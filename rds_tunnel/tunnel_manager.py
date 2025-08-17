import time
import sys
import multiprocessing
import sshtunnel
import mysql.connector
import logging

sshtunnel_logger = logging.getLogger('sshtunnel')
mysql_logger = logging.getLogger('mysql.connector')

def run_tunnel(config):
	"""A function to start and maintain the SSH tunnel."""
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