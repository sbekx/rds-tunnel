import json
import logging
import os

import boto3

config_logger = logging.getLogger('config.loader')
aws_logger = logging.getLogger('aws.boto3')

class ConfigManager:
	"""Manages application configuration, including file loading and secrets fetching."""
	def __init__(self, config_path=None):
		self.config_path = self._resolve_config_path(config_path)

	def _resolve_config_path(self, config_path):
		"""Resolves the path to the user configuration file. Ensures ~/.rdst/ exists and the file is created."""
		rdst_dir = os.path.join(os.path.expanduser("~"), '.rdst')

		# Always keep config files under ~/.rdst/; use the basename of any provided path
		filename = os.path.basename(config_path) if config_path else 'tunnel_config.json'
		path = os.path.join(rdst_dir, filename)

		# Create an empty JSON config file if it doesn't exist
		if not os.path.exists(path):
			try:
				with open(path, 'w') as f:
					f.write('{}\n')
			except Exception as e:
				config_logger.error(f"Failed to create config file {path}: {e}")
				raise

		return path

	def load_config(self):
		"""Loads configuration from the JSON file."""
		config = {}
		# Include INSTANCE_ID/AWS_PROFILE/AWS_REGION so callers can trigger SSM port-forwarding
		keys = [
			'SSH_HOST', 'SSH_USER', 'SSH_PRIVATE_KEY_PATH',
			'DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'DB_NAME', 'LOCAL_PORT',
			'INSTANCE_ID', 'AWS_PROFILE', 'AWS_REGION', 'SECRETS_MANAGER_SECRET_NAME'
		]

		if not os.path.exists(self.config_path):
			config_logger.warning(f"Config file not found at {self.config_path}")
			return {}

		config_logger.info(f"❓ Loading config from {self.config_path}")
		with open(self.config_path, 'r') as f:
			file_config = json.load(f)
		
		for key in keys:
			config[key] = file_config.get(key)
		
		# Set defaults for ports
		config['DB_PORT'] = int(config.get('DB_PORT', 3306))
		config['LOCAL_PORT'] = int(config.get('LOCAL_PORT', 3306))

		# Ensure AWS region default
		config['AWS_REGION'] = config.get('AWS_REGION', 'us-east-1')

		# Mask password for logging
		log_config = config.copy()
		if 'DB_PASSWORD' in log_config:
			log_config['DB_PASSWORD'] = '********'
		config_logger.info(f"✅ Config Loaded: {log_config}")
		return config

	def fetch_from_aws(self, secret_name, region_name):
		"""Fetches configuration from AWS Secrets Manager and saves it."""
		try:
			session = boto3.session.Session()
			client = session.client(service_name='secretsmanager', region_name=region_name)
			secret_value = client.get_secret_value(SecretId=secret_name)
			secrets = json.loads(secret_value['SecretString'])
			with open(self.config_path, 'w') as f:
				json.dump(secrets, f, indent=2)
			print(f"✅ Configuration saved to {self.config_path}")
		except Exception as e:
			aws_logger.error(f"Failed to fetch or save secrets: {e}")
			raise

	def show_config(self):
		"""Shows the current configuration from the file."""
		if os.path.exists(self.config_path):
			print(f"Current configuration in {self.config_path}:")
			with open(self.config_path, 'r') as f:
				print(f.read())
		else:
			config_logger.error(f"Configuration file not found at {self.config_path}")

	def clean_config(self):
		"""Resets the configuration to the default file."""
		default_config_path = os.path.join(os.path.dirname(__file__), 'defaults.json')
		if os.path.exists(default_config_path):
			with open(default_config_path, 'r') as f_in, open(self.config_path, 'w') as f_out:
				f_out.write(f_in.read())
			print(f"Configuration reset to default using {default_config_path}")
		else:
			config_logger.error(f"Default configuration file not found at {default_config_path}")

	def boto_session_from_config(self):
		"""Return a boto3.Session using AWS_PROFILE and AWS_REGION from the file if available."""
		cfg = {}
		if os.path.exists(self.config_path):
			with open(self.config_path, 'r') as f:
				cfg = json.load(f)
		profile = cfg.get('AWS_PROFILE', 'default')
		region = cfg.get('AWS_REGION', 'us-east-1')
		if profile:
			return boto3.session.Session(profile_name=profile, region_name=region)
		return boto3.session.Session(region_name=region)