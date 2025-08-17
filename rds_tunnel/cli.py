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
import sys
import os
import signal
import json
import argparse
import logging
import time

from .config_manager import ConfigManager
from .tunnel_manager import start_tunnel_process, test_db_connection
from .daemon import daemonize
from .garbage_collection import collector, clean

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

	# 4. Create and configure the FileHandler (always active)
	log_file_path = os.path.expanduser("~/.rdstunnel.log")
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
	state_file = os.path.expanduser("~/.rdstunnel.state")
	
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

	state_file = os.path.expanduser("~/.rdstunnel.state")
	user_config_path = os.path.join(os.path.expanduser("~"), '.rdstunnel_config.json')

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
		cli_logger.info("\nCheck tunnel status with:\n -$ rds-tunnel status")
		cli_logger.info("\nIf the tunnel is not active, check the logs.")
		cli_logger.info(f"\nLogs being written to: {os.path.expanduser('~/.rdstunnel.log')}\nRun:\n -$ tail -f ~/.rdstunnel.log")
		# The following code only runs in the daemon process
		
		config_path_to_save = args.config_file or user_config_path
		state = {"pid": os.getpid(), "config_file": os.path.abspath(config_path_to_save)}
		with open(state_file, 'w') as f:
			json.dump(state, f)
		
		# This will redirect stdout and stderr to the log file in the daemon process
		log_file = open(os.path.expanduser("~/.rdstunnel.log"), 'a+')

		os.dup2(log_file.fileno(), sys.stdin.fileno())
		os.dup2(log_file.fileno(), sys.stdout.fileno())
		os.dup2(log_file.fileno(), sys.stderr.fileno())
		
		main(args)

	elif args.command == 'stop':
		if not os.path.exists(state_file):
			cli_logger.info("Tunnel is not running (state file not found).")
			sys.exit(0)
		with open(state_file, 'r') as f:
			try:
				state = json.load(f)
				pid = state.get("pid")
			except json.JSONDecodeError:
				cli_logger.error("Error reading state file. It might be corrupted.")
				sys.exit(1)

		if not pid:
			cli_logger.error("Could not find PID in state file.")
			sys.exit(1)

		try:
			os.kill(pid, signal.SIGTERM)
			cli_logger.info(f"Sent stop signal to tunnel process with PID {pid}.")
			cli_logger.info("Tunnel & DB Connection Terminated.")
		except ProcessLookupError:
			cli_logger.warning(f"Process with PID {pid} not found. It might have already stopped. Cleaning up state file.")
			os.remove(state_file)
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