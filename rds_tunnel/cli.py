try:
	# Suppress noisy deprecation warnings from paramiko/cryptography as early as possible
	import warnings
	warnings.filterwarnings(
		"ignore",
		category=DeprecationWarning,
		module="paramiko"
	)
	try:
		from cryptography.utils import CryptographyDeprecationWarning
		warnings.filterwarnings(
			"ignore",
			category=CryptographyDeprecationWarning,
			module="paramiko"
		)
	except Exception:
		# cryptography may not be available at import time; ignore if so
		pass
except Exception:
	# Best-effort suppression; do not fail if warnings/cryptography modules missing
	pass

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from shutil import which

import boto3

from .config_manager import ConfigManager
from .daemon import daemonize
from .garbage_collection import clean, collector
from .tunnel_manager import start_tunnel_process, test_db_connection

cli_logger = logging.getLogger('cli')
config_logger = logging.getLogger('config.loader')
aws_logger = logging.getLogger('aws.boto3')
sshtunnel_logger = logging.getLogger('sshtunnel')
mysql_logger = logging.getLogger('mysql.connector')

def setup_logging(debug=False):
	"""
	Configures a root logger with a FileHandler and a StreamHandler.
	- FileHandler always logs DEBUG-level messages to ~/.rdstunnel.log.
	- StreamHandler logs INFO/DEBUG messages to the console.
	"""
	# 1. Get the root logger
	root_logger = logging.getLogger()
	
	# 2. Clear any existing handlers to avoid duplicates from repeated calls
	if root_logger.hasHandlers():
		root_logger.handlers.clear()

	# 3. Set the root logger level to DEBUG so no messages are filtered out
	# at the top level. The handlers will handle the specific filtering.
	root_logger.setLevel(logging.DEBUG)

	# Ensure the directory exists for logs and configs
	rdst_dir = os.path.join(os.path.expanduser("~"), '.rdst')
	try:
		os.makedirs(rdst_dir, exist_ok=True)
	except Exception as e:
		config_logger.error(f"Failed to create config directory {rdst_dir}: {e}")
		raise

	# 4. Create and configure the FileHandler (always active)
	log_file_path = os.path.expanduser("~/.rdst/tunnel.log")
	collector(log_file_path=log_file_path)

	file_handler = logging.FileHandler(log_file_path, mode='a')
	file_handler.setLevel(logging.DEBUG) # Always logs DEBUG level and higher
	file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
	file_handler.setFormatter(file_formatter)
	root_logger.addHandler(file_handler)

	# 5. Create and configure the StreamHandler (for terminal output)
	console_handler = logging.StreamHandler(sys.stdout)
	
	# Set the level of the StreamHandler based on the --debug flag
	if debug:
		console_handler.setLevel(logging.DEBUG) # Show DEBUG messages in terminal
	else:
		console_handler.setLevel(logging.INFO) # Default to INFO messages
		
	console_formatter = logging.Formatter('%(message)s') # Simpler format for the terminal
	console_handler.setFormatter(console_formatter)
	root_logger.addHandler(console_handler)

	# 6. Ensure loggers do not propagate to the root logger again (optional, but good practice)
	# The default is to propagate, so we don't need to change it, but it's good to be aware.

def main(args):
	"""Main execution logic for the tunnel daemon."""
	state_file = os.path.expanduser("~/.rdst/tunnel.state")
	
	def sigterm_handler(_signum, _frame):
		raise KeyboardInterrupt

	signal.signal(signal.SIGTERM, sigterm_handler)

	config_manager = ConfigManager(config_path=args.config_file)
	config = config_manager.load_config()
	if not config:
		cli_logger.error("❌ Configuration could not be loaded. Exiting.")
		sys.exit(1)

	tunnel_process = start_tunnel_process(config)
	cli_logger.info("Tunnel process started. Waiting 2 seconds for connection to establish...")
	time.sleep(2)
	
	cli_logger.debug("Testing DB connection...")
	test_db_connection(config)

	cli_logger.info("Tunnel is active. The main process will now run in the background to keep the tunnel alive.")

	try:
		while True:
			time.sleep(1)
	except KeyboardInterrupt:
		cli_logger.warning("⏹️  Interrupt - Main app terminated.")
	except Exception as e:
		cli_logger.error(f"❌ An error occurred during main execution: {e}")
	finally:
		if tunnel_process.is_alive():
			cli_logger.warning("Shutting down tunnel process...")
			tunnel_process.terminate()
			tunnel_process.join()
		if os.path.exists(state_file):
			os.remove(state_file)


def cli():
	"""Handles the command-line interface logic."""
	parser = argparse.ArgumentParser(description="RDS Tunnel CLI", add_help=False)
	parser.add_argument('-h', '--help', action='store_true', help='Show this help message and exit.')
	# parser.add_argument('--debug', action='store_true', help='Enable debug logging for the current command.')
	subparsers = parser.add_subparsers(dest='command', help='Available commands')

	# Start command
	start_parser = subparsers.add_parser('start', help='Start the RDS tunnel daemon')
	start_parser.add_argument('--config-file', type=str, help='Specify a custom configuration file path')

	# Stop command
	stop_parser = subparsers.add_parser('stop', help='Stop the RDS tunnel daemon')

	# Status command
	subparsers.add_parser('status', help='Check the status of the RDS tunnel')

	# Config command
	config_parser = subparsers.add_parser('config', help='Manage configuration')
	config_group = config_parser.add_mutually_exclusive_group(required=True)
	config_group.add_argument('--fetch', action='store_true', help='Fetch configuration from AWS Secrets Manager')
	config_group.add_argument('--show', action='store_true', help='Show the current configuration')
	config_group.add_argument('--clean', action='store_true', help='Reset the configuration to default')

	# Logs command
	logs_parser = subparsers.add_parser('logs', help='Show or clean logs')
	logs_parser_group = logs_parser.add_mutually_exclusive_group(required=True)
	logs_parser_group.add_argument('--show', action='store_true', help='Show the current logs')
	logs_parser_group.add_argument('--clean', action='store_true', help='Clean the logs (THIS WILL EMPTY THE LOGS FILE)')

	# Help command
	subparsers.add_parser('help', help='Show this help message and exit.')

	args, unknown = parser.parse_known_args()

	# Call setup_logging right away to ensure it's always configured
	setup_logging()

	def _get_process_cmd(pid):
		"""Return the command line for pid or None if unavailable."""
		try:
			out = os.popen(f"ps -p {int(pid)} -o command=").read().strip()
			return out if out else None
		except Exception:
			return None


	state_file = os.path.expanduser("~/.rdst/tunnel.state")
	user_config_path = os.path.join(os.path.expanduser("~"), '.rdst/tunnel_config.json')

	if args.help or args.command == 'help':
		parser.print_help()
		sys.exit(0)

	if not args.command:
		parser.print_help()
		sys.exit(0)

	if args.command == 'start':
		if os.path.exists(state_file):
			with open(state_file, 'r') as f:
				try:
					state = json.load(f)
					pid = state.get("pid")
					if pid and os.kill(pid, 0) is None:
						cli_logger.error(f"Tunnel is already running with PID {pid}.")
						sys.exit(1)
				except (json.JSONDecodeError, OSError):
					cli_logger.debug("Found stale state file. Cleaning up.")
					os.remove(state_file)
		
		cli_logger.info("Starting tunnel in daemon mode...")
		
		# Now use the daemonize() function to handle the forking
		daemonize()
		cli_logger.info("\nCheck tunnel status with:\n -$ rdst status")
		cli_logger.info("\nIf the tunnel is not active, check the logs.")
		cli_logger.info(f"\nLogs being written to: {os.path.expanduser('~/.rdst/tunnel.log')}\nRun:\n -$ tail -f ~/.rdst/tunnel.log")
		# The following code only runs in the daemon process
		
		config_path_to_save = args.config_file or user_config_path
		state = {"pid": os.getpid(), "config_file": os.path.abspath(config_path_to_save)}
		with open(state_file, 'w') as f:
			json.dump(state, f)
		
		# This will redirect stdout and stderr to the log file in the daemon process
		log_file = open(os.path.expanduser("~/.rdst/tunnel.log"), 'a+')

		os.dup2(log_file.fileno(), sys.stdin.fileno())
		os.dup2(log_file.fileno(), sys.stdout.fileno())
		os.dup2(log_file.fileno(), sys.stderr.fileno())
		
		main(args)

	elif args.command == 'stop':
		# If no state file, nothing to stop
		if not os.path.exists(state_file):
			cli_logger.info("Tunnel is not running (state file not found).")
			sys.exit(0)

		# Load the state
		try:
			with open(state_file, 'r') as f:
				state = json.load(f)
		except Exception:
			cli_logger.error("Error reading state file. It might be corrupted or missing.")
			sys.exit(1)

		pid = state.get('pid')
		if not pid:
			cli_logger.error("Could not find PID in state file.")
			sys.exit(1)

		# 1) Try to stop any recorded SSM session (by PID)
		ssm_pid = state.get('ssm_pid')
		ssm_session_id = state.get('ssm_session_id')

		# Load AWS related config values early so they are available for the
		# ssm_session_id termination path (avoid undefined-name errors).
		instance_id = None
		aws_profile = None
		aws_region = None
		try:
			config_path = state.get('config_file')
			if config_path and os.path.exists(config_path):
				with open(config_path, 'r') as cf:
					cfg = json.load(cf)
					instance_id = cfg.get('INSTANCE_ID')
					aws_profile = cfg.get('AWS_PROFILE')
					aws_region = cfg.get('AWS_REGION')
		except Exception:
			# fall back to None if anything goes wrong
			instance_id = instance_id or None
			aws_profile = aws_profile or None
			aws_region = aws_region or None

		# Also allow user-level config to populate any missing values
		try:
			user_cfg = os.path.expanduser('~/.rdst/tunnel_config.json')
			if os.path.exists(user_cfg):
				with open(user_cfg, 'r') as cf:
					cfg = json.load(cf)
					if not instance_id:
						instance_id = cfg.get('INSTANCE_ID')
					if not aws_profile:
						aws_profile = cfg.get('AWS_PROFILE')
					if not aws_region:
						aws_region = cfg.get('AWS_REGION')
		except Exception:
			# ignore and continue with whatever we have
			pass

		# If we have a recorded session id, only terminate that session and (optionally) our recorded pid.
		if ssm_session_id:
			terminated = False
			# Try boto3 terminate (preferred)
			try:
				if aws_profile:
					boto_sess = boto3.session.Session(profile_name=aws_profile, region_name=aws_region)
				else:
					boto_sess = boto3.session.Session(region_name=aws_region)
				ssm_client = boto_sess.client('ssm')
				try:
					ssm_client.terminate_session(SessionId=ssm_session_id)
					cli_logger.info(f"Terminated SSM session {ssm_session_id} via boto3")
					terminated = True
				except Exception as e:
					cli_logger.debug(f"boto3 terminate_session failed for {ssm_session_id}: {e}")
			except Exception as e:
				cli_logger.debug(f"Could not initialize boto3 session/client: {e}")

			# Fallback to aws cli terminate-session for this single session id
			if not terminated:
				try:
					aws_cli = which('aws')
					if aws_cli:
						terminate_cmd = [aws_cli, 'ssm', 'terminate-session', '--session-id', ssm_session_id]
						if aws_region:
							terminate_cmd.extend(['--region', aws_region])
						if aws_profile:
							terminate_cmd.extend(['--profile', aws_profile])
						try:
							out = subprocess.check_output(terminate_cmd, text=True)
							print(out.strip())
							cli_logger.info(f"Terminated SSM session {ssm_session_id} for instance {instance_id}")
							terminated = True
						except Exception as e:
							cli_logger.debug(f"aws CLI terminate-session failed for {ssm_session_id}: {e}")
				except Exception:
					pass

			# After attempting to terminate the session by id, optionally stop the local client we started
			if ssm_pid:
				try:
					cmd = _get_process_cmd(ssm_pid)
				except Exception:
					cmd = None

				if cmd and 'aws' in cmd and 'start-session' in cmd:
					try:
						os.killpg(int(ssm_pid), signal.SIGTERM)
						time.sleep(1)
						try:
							os.killpg(int(ssm_pid), signal.SIGKILL)
						except Exception:
							pass
					except ProcessLookupError:
						cli_logger.debug(f"SSM pid {ssm_pid} not found; might have already exited.")
					except Exception as e:
						cli_logger.debug(f"Error terminating SSM client process: {e}")

			# Clear session id and pid from state
			try:
				if 'ssm_session_id' in state:
					del state['ssm_session_id']
				if 'ssm_pid' in state:
					del state['ssm_pid']
				with open(state_file, 'w') as f:
					json.dump(state, f)
			except Exception:
				pass

				# handled recorded session-id; no fallback scanning will run
				pass

		# 2) Remove ssm_pid from state (best-effort)
		try:
			if 'ssm_pid' in state:
				del state['ssm_pid']
			with open(state_file, 'w') as f:
				json.dump(state, f)
		except Exception:
			pass

		# Fallback logic removed: per user request we only ever terminate the
		# specific session-id recorded when `rdst start` ran. We do not scan
		# local processes or describe/terminate other sessions.

		# 4) Finally, stop the daemon process
		try:
			os.kill(int(pid), signal.SIGTERM)
			cli_logger.info(f"Sent stop signal to tunnel process with PID {pid}.")
			cli_logger.info("Tunnel & DB Connection Terminated.")
		except ProcessLookupError:
			cli_logger.warning(f"Process with PID {pid} not found. It might have already stopped. Cleaning up state file.")
			try:
				os.remove(state_file)
			except Exception:
				pass
		except Exception as e:
			cli_logger.error(f"An error occurred while stopping the tunnel: {e}")

	elif args.command == 'status':
		if not os.path.exists(state_file):
			cli_logger.info("Tunnel: Inactive")
			sys.exit(0)
		
		try:
			with open(state_file, 'r') as f:
				state = json.load(f)
				pid = state.get("pid")
				config_path = state.get("config_file")
		except (json.JSONDecodeError, FileNotFoundError):
			cli_logger.info("Tunnel: Inactive (Could not read state file)")
			sys.exit(1)

		if not pid:
			cli_logger.info("Tunnel: Inactive (No PID in state file)")
			sys.exit(1)

		try:
			os.kill(pid, 0)
			cli_logger.info("Tunnel: Active")
			config = ConfigManager(config_path).load_config()
			if not config:
				cli_logger.info("Database: Unknown (Could not load config)")
				sys.exit(1)

			if test_db_connection(config):
				cli_logger.info("Database: Connected")
				cli_logger.info(f"  - Bound to: 127.0.0.1:{config.get('LOCAL_PORT')}")
			else:
				cli_logger.info("Database: Disconnected")

			# Show SSM session info if present
			try:
				with open(state_file, 'r') as f:
					state = json.load(f)
			except Exception:
				state = {}
			ssm_pid = state.get('ssm_pid')
			ssm_session_id = state.get('ssm_session_id')
			if ssm_pid:
				cmd = _get_process_cmd(ssm_pid)
				cli_logger.info(f"SSM session: \n  - pid={ssm_pid} \n  - cmd={cmd}")
			if ssm_session_id:
				cli_logger.info(f"SSM session-id: {ssm_session_id}")

		except OSError:
			cli_logger.info("Tunnel: Inactive (Process not found)")
			os.remove(state_file)
	
	elif args.command == 'config':
		config_manager = ConfigManager()
		if args.fetch:
			secret_name = input("Enter the AWS Secrets Manager secret name: ")
			region_name = input("Enter the AWS region (e.g., us-east-1): ")
			cli_logger.info(f"Fetching secrets from {secret_name} in {region_name}...")
			config_manager.fetch_from_aws(secret_name, region_name)
		elif args.show:
			config_manager.show_config()
		elif args.clean:
			config_manager.clean_config()

	elif args.command == "logs":
		log_file_path = os.path.expanduser("~/.rdstunnel.log")
		if args.show:
			cli_logger.info(f"Displaying logs from: {log_file_path}")
			if sys.platform == "win32":
				# For Windows, a simple type command or more advanced PowerShell
				# For continuous tail-like behavior, a loop might be needed
				cli_logger.info("On Windows, you might need to use 'Get-Content -Path ~/.rdstunnel.log -Wait' in PowerShell.")
				os.system(f"type {log_file_path}")
			else:
				# For Unix-like systems, use tail -f
				os.system(f"tail -f {log_file_path}") # This will block until the user exits tail
		elif args.clean:
			confirm = input(f"This action will delete all log entries in {log_file_path}.\nAre you sure you want to clean the logs? (y/n): ").lower()
			if confirm == 'y':
				clean(log_file_path=log_file_path)
				cli_logger.info(f"Cleaned log file: {log_file_path}")
			else:
				cli_logger.info("Log cleaning cancelled.")

if __name__ == '__main__':
	cli()