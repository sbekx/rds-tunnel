# All of the below just so my CLI tool will look pretty:
# Origin Error:
# /Users/seb/.pyenv/versions/3.13.3/lib/python3.13/site-packages/paramiko/pkey.py:82: CryptographyDeprecationWarning: TripleDES has been moved to cryptography.hazmat.decrepit.ciphers.algorithms.TripleDES and will be removed from cryptography.hazmat.primitives.ciphers.algorithms in 48.0.0.
#   "cipher": algorithms.TripleDES,
# /Users/seb/.pyenv/versions/3.13.3/lib/python3.13/site-packages/paramiko/transport.py:253: CryptographyDeprecationWarning: TripleDES has been moved to cryptography.hazmat.decrepit.ciphers.algorithms.TripleDES and will be removed from cryptography.hazmat.primitives.ciphers.algorithms in 48.0.0.
#   "class": algorithms.TripleDES,
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
except ImportError:
	pass
# End
import time
import sys
import os

import logging
import json
import boto3
import argparse

import sshtunnel
import multiprocessing
import mysql.connector


# Set up logging for both sshtunnel and mysql.connector
logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
	stream=sys.stdout
)
config_logger = logging.getLogger('config.loader')
config_logger.setLevel(logging.INFO)
aws_logger = logging.getLogger('aws.boto3')
aws_logger.setLevel(logging.INFO)
sshtunnel_logger = logging.getLogger('sshtunnel')
sshtunnel_logger.setLevel(logging.INFO)
mysql_logger = logging.getLogger('mysql.connector')
mysql_logger.setLevel(logging.DEBUG)

def load_env_and_secrets():
	"""Loads configuration from file, environment, or AWS Secrets Manager."""
	config = {}
	config_logger.info("❓Loading configuration")
	keys = ['SSH_HOST', 'SSH_USER', 'SSH_PRIVATE_KEY_PATH', 'DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'DB_NAME', 'LOCAL_PORT']
	# The primary config file is in the user's home directory.
	# If it doesn't exist, we'll copy it from the local directory if available.
	home_dir = os.path.expanduser("~")
	config_path = os.path.join(home_dir, '.rdstunnel_config.json')
	default_config_path = os.path.join(os.path.dirname(__file__), 'config.json')

	if os.path.exists(default_config_path) and not os.path.exists(config_path):
		config_logger.info(f"Config file not found at {config_path}, copying from {default_config_path}")
		with open(default_config_path, 'r') as f_in, open(config_path, 'w') as f_out:
			f_out.write(f_in.read())

	# Try to load config from file first
	if os.path.exists(config_path):
		config_logger.info(f"❓Loading config from {config_path}")
		with open(config_path, 'r') as f:
			file_config = json.load(f)
			config_logger.debug(f"Current config: {file_config}")
		for key in keys:
			config[key] = file_config.get(key)
	else:
		# Try to load from environment
		for key in keys:
			config[key] = os.getenv(key)

	# If any required config missing, fetch from AWS Secrets Manager
	config_logger.debug(f"Config: {config}")
	if not all(config.get(var) for var in keys):
		aws_logger.info("❓Config missing, fetching from Secrets Manager...")
		secret_name = config.get('SECRETS_MANAGER_SECRET_NAME', 'tool/rds-tunnel-staging')
		region_name =config.get('AWS_REGION', 'us-east-1')
		if secret_name:
			session = boto3.session.Session()
			client = session.client(service_name='secretsmanager', region_name=region_name)
			secret_value = client.get_secret_value(SecretId=secret_name)
			secrets = json.loads(secret_value['SecretString'])
			for key in keys:
				if secrets.get(key):
					config[key] = str(secrets[key])
			# Save config to file for future use
			with open(config_path, 'w') as f:
				json.dump({k: config[k] for k in keys}, f, indent=2)
				aws_logger.info("Getting missing keys from Secrets Manager")
		else:
			aws_logger.warning("❌ SECRETS_MANAGER_SECRET_NAME not set in environment variables.")

	# Set defaults for ports if not present
	config['DB_PORT'] = int(config.get('DB_PORT', 3306))
	config['LOCAL_PORT'] = int(config.get('LOCAL_PORT', 3306))

	config_logger.info(f"Config Loaded: {config}")
	return config

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

def main():
	# Load configuration once at the start
	config = load_env_and_secrets()

	# Start the tunnel in a separate daemon process, passing the config
	tunnel_process = multiprocessing.Process(target=run_tunnel, args=(config,), daemon=True)
	tunnel_process.start()

	# Wait a moment for the tunnel to establish
	time.sleep(5)

	mysql_logger.info("Main script running. You can now execute your local Lambda code.")
	mysql_logger.info("Press Ctrl+C to terminate the tunnel and exit.")

	# Testing database connection for example:
	try:
		conn = mysql.connector.connect(
			user=config['DB_USER'],
			password=config['DB_PASSWORD'],
			host='127.0.0.1',
			port=config['LOCAL_PORT'],
			database=config['DB_NAME']
		)

		mysql_logger.info("✅ Successfully connected to MySQL through the tunnel!")
		cursor = conn.cursor()
		query = "SELECT * FROM ent_orgs LIMIT 1;"
		mysql_logger.debug(f"Executing test query: \n{query}")
		cursor.execute(query)
		for row in cursor.fetchall():
			mysql_logger.debug(f"Result: \n{row}")
		cursor.close()
		conn.close()
		mysql_logger.debug("✅ MySQL connection closed.")
		export_cmd = (
			f"export DB_USER='{config['DB_USER']}'\n"
			f"export DB_PASSWORD='{config['DB_PASSWORD']}'\n"
			f"export DB_HOST='127.0.0.1'\n"
			f"export DB_PORT='{config['LOCAL_PORT']}'\n"
			f"export DB_NAME='{config['DB_NAME']}'"
		)
		mysql_logger.info("🔑 To connect locally, run:\n" + export_cmd)
		mysql_logger.info("✅ MySQL tunnel still active and ready for connections.")

		# Keep the main process alive until you manually terminate it
		while True:
			time.sleep(1)

	except KeyboardInterrupt:
		mysql_logger.warning("Main script terminated.")
	except Exception as e:
		mysql_logger.error(f"❌ An error occurred during main execution: {e}")
	finally:
		if tunnel_process.is_alive():
			mysql_logger.warning("Shutting down tunnel process...")
			tunnel_process.terminate()
			tunnel_process.join()


def cli():
	print("\nDEPRECATION NOTICE\nCommand: 'rds-tunnel' is deprecated and will be removed in a future version.\nIt has been replaced by 'rdst'.\n\n")

	parser = argparse.ArgumentParser(description="RDS Tunnel CLI")
	parser.add_argument('--staging', action='store_true', help='Run staging tunnel')
	parser.add_argument('--production', action='store_true', help='Run production tunnel (not implemented)')
	parser.add_argument('--loaddev', action='store_true', help='Load required environment variables')
	args = parser.parse_args()

	if args.staging:
		main()
	elif args.production:
		print("\n\nComing soon, not currently implemented")
	elif args.loaddev:
		load_env_and_secrets()
	else:
		parser.print_help()

if __name__ == '__main__':
	cli()