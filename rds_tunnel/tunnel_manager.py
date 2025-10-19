import json
import logging
import multiprocessing
import os
import re
import select
import subprocess
import time
from shutil import which

import mysql.connector
import sshtunnel

sshtunnel_logger = logging.getLogger('sshtunnel')
mysql_logger = logging.getLogger('mysql.connector')


def _state_file_path():
	return os.path.expanduser('~/.rdst/tunnel.state')


def _write_ssm_pid(pid):
	"""Write ssm_pid into the main state file atomically if it exists."""
	state_file = _state_file_path()
	try:
		state = {}
		if os.path.exists(state_file):
			with open(state_file, 'r') as f:
				state = json.load(f)
		state['ssm_pid'] = int(pid)
		with open(state_file, 'w') as f:
			json.dump(state, f)
	except Exception:
		sshtunnel_logger.debug("Could not write ssm_pid to state file")


def _clear_ssm_pid():
	state_file = _state_file_path()
	try:
		if not os.path.exists(state_file):
			return
		with open(state_file, 'r') as f:
			state = json.load(f)
		if 'ssm_pid' in state:
			del state['ssm_pid']
		if 'ssm_session_id' in state:
			del state['ssm_session_id']
		with open(state_file, 'w') as f:
			json.dump(state, f)
	except Exception:
		sshtunnel_logger.debug("Could not clear ssm_pid from state file")


def _write_ssm_session(session_id):
	"""Write the SSM session id into the main state file atomically if it exists."""
	state_file = _state_file_path()
	try:
		state = {}
		if os.path.exists(state_file):
			with open(state_file, 'r') as f:
				state = json.load(f)
		state['ssm_session_id'] = session_id
		with open(state_file, 'w') as f:
			json.dump(state, f)
	except Exception:
		sshtunnel_logger.debug("Could not write ssm_session_id to state file")

def run_tunnel(config):
	"""A function to start and maintain the SSH tunnel."""
	# If INSTANCE_ID provided, prefer using AWS SSM port forwarding session
	if config.get('INSTANCE_ID'):
		aws_cli = which('aws')
		if not aws_cli:
			sshtunnel_logger.error("❌ aws CLI not found in PATH; cannot start SSM port-forwarding session.")
			return

		instance_id = config.get('INSTANCE_ID')
		if not instance_id:
			sshtunnel_logger.error("❌ INSTANCE_ID not provided for SSM port-forwarding")
			return

		host = config.get('DB_HOST')
		port = str(config.get('DB_PORT', 3306))
		local_port = str(config.get('LOCAL_PORT', 3306))
		region = config.get('AWS_REGION') or 'us-east-1'
		profile = config.get('AWS_PROFILE')

		params = json.dumps({
			"host": [host],
			"portNumber": [port],
			"localPortNumber": [local_port],
		})

		cmd_parts = [aws_cli, 'ssm', 'start-session', '--target', instance_id, '--document-name', 'AWS-StartPortForwardingSessionToRemoteHost', '--parameters', params, '--region', region]
		if profile:
			cmd_parts.extend(['--profile', profile])

		sshtunnel_logger.info(f"🔁 Starting SSM port-forwarding session to {instance_id} (local:{local_port} -> {host}:{port})")
		sshtunnel_logger.debug(f"Command parts: {cmd_parts}")
		try:
			# Start aws CLI as a managed child process in its own session (so it has its own pgid)
			# Start aws CLI as a managed child process in its own session (so it has its own pgid)
			# Start aws CLI and capture stdout so we can extract the SessionId printed by the CLI
			proc = subprocess.Popen(cmd_parts, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True)
			sshtunnel_logger.info(f"✅ SSM port-forwarding session started (pid={proc.pid}).")

			# Persist pid into main state file so CLI commands can find it
			_write_ssm_pid(proc.pid)

			# Try to read initial stdout lines to capture the SessionId printed by aws cli
			session_id = None
			start_time = time.time()
			# Accept multiple textual forms that mention a SessionId
			pattern = re.compile(r"SessionId[:\s]+(\S+)|sessionId[:\s]+(\S+)", re.IGNORECASE)
			try:
				# wait up to 15 seconds for session id to appear (some environments buffer stdout)
				while time.time() - start_time < 15:
					ready, _, _ = select.select([proc.stdout], [], [], 0.5)
					if not ready:
						continue
					line = proc.stdout.readline()
					if not line:
						break
					# Log the CLI output at debug level to assist diagnosis
					sshtunnel_logger.debug(f"aws ssm start-session output: {line.strip()}")
					m = pattern.search(line)
					if m:
						session_id = m.group(1) or m.group(2)
						if session_id:
							_write_ssm_session(session_id)
							sshtunnel_logger.info(f"✅ Detected SSM SessionId={session_id} and recorded to state file")
							break
			except Exception:
				# If we can't read or parse, continue without session id
				sshtunnel_logger.debug("Failed while attempting to read aws CLI output for SessionId")

			# Wait for the child to exit (this keeps the tunnel process alive)
			try:
				proc.wait()
			except KeyboardInterrupt:
				# If the parent gets interrupted, ensure child is terminated
				try:
					os.killpg(proc.pid, 15)
				except Exception:
					pass
				raise
			finally:
				# Clear ssm_pid from state when the child exits/we exit
				_clear_ssm_pid()
		except Exception as e:
			sshtunnel_logger.error(f"❌ Failed to start SSM session: {e}")
		return

	# Fallback to SSH tunnel if INSTANCE_ID not provided
	try:
		with sshtunnel.SSHTunnelForwarder(
			(config['SSH_HOST'], 22),
			ssh_username=config['SSH_USER'],
			ssh_pkey=config['SSH_PRIVATE_KEY_PATH'],
			remote_bind_address=(config['DB_HOST'], config['DB_PORT']),
			local_bind_address=('127.0.0.1', config['LOCAL_PORT'])
		) as tunnel:
			sshtunnel_logger.debug(f"✅ SSH tunnel started on localhost:{config['LOCAL_PORT']}")
			while tunnel.is_active:
				time.sleep(1)
	except Exception as e:
		sshtunnel_logger.error(f"❌ Tunnel process error: {e}")

def test_db_connection(config):
	"""Tests the database connection through the local tunnel."""
	try:
		mysql_logger.info("Attempting to connect to database through the tunnel...")
		conn = mysql.connector.connect(
			user=config.get('DB_USER'),
			password=config.get('DB_PASSWORD'),
			host='127.0.0.1',
			port=config.get('LOCAL_PORT'),
			database=config.get('DB_NAME'),
			connection_timeout=10
		)
		if conn.is_connected():
			mysql_logger.info("✅ Successfully connected to MySQL through the tunnel!")
			conn.close()
			mysql_logger.debug("✅ MySQL test connection closed.")
			return True
		else:
			mysql_logger.error("❌ Connection to database failed.")
			return False
	except mysql.connector.Error as err:
		mysql_logger.error(f"❌ Failed to connect to database: {err}")
		return False
	except Exception as e:
		mysql_logger.error(f"❌ An unexpected error occurred during the test connection: {e}")
		return False

def start_tunnel_process(config):
	"""Starts the tunnel in a separate multiprocessing process."""
	tunnel_process = multiprocessing.Process(target=run_tunnel, args=(config,), daemon=True)
	tunnel_process.start()
	return tunnel_process