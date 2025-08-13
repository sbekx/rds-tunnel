<!-- 
    TODO 
    - Add in badges when CI/CD is complete
    - Include PR template and Issue template
-->

# 🚀 RDS Tunnel

A simple command-line interface (CLI) tool designed to establish and manage SSH tunnels to Amazon RDS (Relational Database Service) instances. This tool supports connecting to MySQL and PostgreSQL databases via an SSH bastion host, facilitating secure local development and testing.

***

## ✨ Features

* **Secure SSH Tunneling**: Establishes a secure tunnel through an SSH bastion host to your RDS instance.
* **Flexible Configuration**: Supports loading configuration from `config.json`, environment variables, or AWS Secrets Manager.
* **MySQL Support**: Built-in test connection for MySQL databases.
* **Multi-process Design**: Runs the SSH tunnel in a separate background process, allowing your main application to run independently.
* **CLI Interface**: Easy-to-use command-line arguments for different environments and tasks.

### Supported OS
|                                                                                                                | Name                 | Status |
| -------------------------------------------------------------------------------------------------------------------- | -------------------- | ------ |
| ![](https://raw.githubusercontent.com/EgoistDeveloper/operating-system-logos/master/src/24x24/MAC.png "MAC (24x24)") | Mac                  | ✅     |
| ![](https://raw.githubusercontent.com/EgoistDeveloper/operating-system-logos/master/src/24x24/RAS.png "RAS (24x24)") | Raspberry Pi         | 🤷🏼‍♂️     |
| ![](https://raw.githubusercontent.com/EgoistDeveloper/operating-system-logos/master/src/24x24/UBT.png "UBT (24x24)") | Ubuntu               | 🤷🏼‍♂️     |
| ![](https://raw.githubusercontent.com/EgoistDeveloper/operating-system-logos/master/src/24x24/WIN.png "WIN (24x24))") | Windows              | ❌    |

***

## 🛠️ Installation

```bash
pip install rds-tunnel
```
### Build it Locally
To run `rds-tunnel` locally, follow these steps:

1.  **Clone the Repository (if applicable)**:
    ```bash
    git clone https://github.com/sbekx/rds-tunnel.git
    cd rds-tunnel
    ```

2.  **Build the Wheel Package**:
    Ensure you have `uv` installed (`brew install uv`). Navigate to the root directory of the project (where `pyproject.toml` is located) and run:
    ```bash
    uv build
    ```
    This command will create a distributable wheel file (e.g., `rds_tunnel-1.0.0-py3-none-any.whl`) in the `dist/` directory.

3.  **Install the Package**:
    Install the generated wheel file using `pip`:
    ```bash
    pip install dist/rds_tunnel-1.0.0-py3-none-any.whl # Adjust filename if different
    ```
    This will install `rds-tunnel` as an executable command on your system.

***

## ⚙️ Configuration & Usage

The `rds-tunnel` tool looks for configuration in the following order:

1.  **`config.json` file**: A `config.json` file in the same directory as `tunnel.py`.
    - This will be located at `/Users/USER/.pyenv/versions/X.X.X/lib/pythonX.X/site-packages/rds_tunnel/config.json` or somewhere similar.
2.  **Environment Variables**: System environment variables.
3.  **AWS Secrets Manager**: If the above are insufficient, it attempts to fetch secrets from AWS Secrets Manager using the secret name `tool/rds-tunnel-staging` and region `us-east-1` (these can be overridden if provided in `config.json` or environment variables). 
    - If relying on the Secrets Manager appoach to set the config, ensure you have created the AWS Secret and your local AWS CLI is configured to access the same AWS account.

**`config.json` Example**:

```json
{
  "SSH_HOST": "your-ssh-bastion-host-ip",
  "SSH_USER": "ec2-user",
  "SSH_PRIVATE_KEY_PATH": "/path/to/your/ssh/private/key.pem",
  "DB_HOST": "your-rds-database-endpoint",
  "DB_PORT": 3306,
  "DB_USER": "your-db-username",
  "DB_PASSWORD": "your-db-password",
  "DB_NAME": "your-database-name",
  "LOCAL_PORT": 3306,
  "SECRETS_MANAGER_SECRET_NAME": "tool/rds-tunnel-staging",
  "AWS_REGION": "us-east-1"
}
```

### Environment Variables
Alternatively, you can set these variables in your shell environment, note that they will still be pulled and set by the `load_env_and_secrets()` function:

```Bash
export SSH_HOST="your-ssh-bastion-host-ip"
export SSH_USER="ec2-user"
export SSH_PRIVATE_KEY_PATH="/path/to/your/ssh/private/key.pem"
export DB_HOST="your-rds-database-endpoint"
export DB_PORT="3306"
export DB_USER="your-db-username"
export DB_PASSWORD="your-db-password"
export DB_NAME="your-database-name"
export LOCAL_PORT="3306"
export SECRETS_MANAGER_SECRET_NAME="tool/rds-tunnel-staging"
export AWS_REGION="us-east-1"
```

### Running the Staging Tunnel
This command starts the SSH tunnel and attempts to connect to the database specified in your configuration. It will keep the tunnel active until you terminate the process (e.g., by pressing Ctrl+C).

```Bash
rds-tunnel --staging
```
Upon successful connection, the tool will print environment variables you can use to connect your local applications, such as Lambda's that use SQL clients or ORMs, to the tunneled database:
```bash
🔑 To connect locally, run:
export DB_USER='your-db-username'
export DB_PASSWORD='your-db-password'
export DB_HOST='127.0.0.1'
export DB_PORT='3306'
export DB_NAME='your-database-name'
```

### Loading Environment Variables (Development)
This command loads the configuration variables (from config.json or Secrets Manager) and prints them to your console. This is useful for debugging or manually setting environment variables for other applications.

```Bash
rds-tunnel --loaddev
```

### Help
To see all available commands:

```Bash
rds-tunnel --help
```

*** 

## 🤝 Contributing
Contributions are welcome! Please feel free to open issues or submit pull requests.