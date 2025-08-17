<!-- 
    TODO 
    - Add in badges when CI/CD is complete
    - Include PR template and Issue template
-->

# 🚀 RDS Tunnel

A simple command-line interface (CLI) tool designed to establish and manage SSH tunnels to Amazon RDS (Relational Database Service) instances. This tool runs as a background daemon, allowing you to set up a secure connection and leave it running.

## Project Background
This tool was created to provide a free and open-source solution to a common developer workflow: securely connecting local applications to a database inside a private network.

While many excellent database extensions exist for editors like VSCode, they sometimes require a premium subscription to share the tunnel connection both inside and outside the editor, rds-tunnel offers a different approach. By running as a standalone background process, it creates a single, persistent tunnel that any application on your system—your IDE, database GUI, or scripts—can use simultaneously.
 
The primary motivation behind this tool was the desire to seamlessly test Lambda functions locally against various database environments, from development to production. 

Initially, this involved manually executing and maintaining a lengthy SSH command:
```bash
ssh -N -L 3306:RDS-DATABASE.cluster-********.us-east-1.rds.amazonaws.com:3306 ec2-user@EC2_HOST_IP_OR_PUBLIC_DNS -i /PATH/TO/KEY.pem
```

After this it became a simple script that I ran as an alias via my .zshrc. This then evolved as my development itch took hold and it became v0.1.0 a simple python script which takes a couple of arguments to start/stop the tunnel. 

Now the CLI tool starts/stops the tunnel and runs in the background, it allows any code I run to interact with the DB over the ssh tunnel that's bound to my local. 
***

## ✨ Features

*   **Secure SSH Tunneling**: Establishes a secure tunnel through an SSH bastion host to your RDS instance.
*   **Daemonized Process**: Runs the SSH tunnel in a separate background process, allowing you to start it and forget it.
*   **Simple JSON Configuration**: Uses a straightforward JSON file (`~/.rdstunnel_config.json`) for all settings.
*   **Interactive Configuration**: Interactively fetch credentials from AWS Secrets Manager to set up your configuration file.
*   **Full CLI Control**: Manage the tunnel with a clear and simple command structure:
    *   `rds-tunnel start`
    *   `rds-tunnel stop`
    *   `rds-tunnel status`
    *   `rds-tunnel config`
    *   `rds-tunnel help`

### Supported OS
I have tried to keep the tool as OS agnostic as possible, however 🤷🏼‍♂️ still applies to everything other Mac.
|                                                                                                                | Name                 | Status |
| -------------------------------------------------------------------------------------------------------------------- | -------------------- | ------ |
| ![](https://raw.githubusercontent.com/EgoistDeveloper/operating-system-logos/master/src/24x24/MAC.png "MAC (24x24)") | Mac                  | ✅     |
| ![](https://raw.githubusercontent.com/EgoistDeveloper/operating-system-logos/master/src/24x24/RAS.png "RAS (24x24)") | Raspberry Pi         | 🤷🏼‍♂️     |
| ![](https://raw.githubusercontent.com/EgoistDeveloper/operating-system-logos/master/src/24x24/UBT.png "UBT (24x24)") | Ubuntu               | 🤷🏼‍♂️     |
| ![](https://raw.githubusercontent.com/EgoistDeveloper/operating-system-logos/master/src/24x24/WIN.png "WIN (24x24))") | Windows              | 🤷🏼‍♂️    |

***

## 🛠️ Installation
### Recommended
```bash
pip install rds-tunnel
```
### (Optional) Build it Locally
To run `rds-tunnel` locally, follow these steps:

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/sbekx/rds-tunnel.git
    cd rds-tunnel
    ```

2.  **Build the Package**:
    Ensure you have `uv` installed. Navigate to the root of the project and run:
    ```bash
    uv build
    ```
    This creates a distributable wheel file (e.g., `rds_tunnel-1.0.0-py3-none-any.whl`) in the `dist/` directory.

3.  **Install the Package**:
    Install the generated wheel file using `pip`. This makes the `rdst` command available system-wide.
    ```bash
    pip install dist/rds_tunnel-*.whl # Adjust filename if different
    ```

***

## ⚙️ Configuration

The `rds-tunnel` tool uses a single configuration file located at `~/.rdstunnel_config.json`.

On the first run, the tool will automatically create this file for you from a default template. You can then manage it using the `rdst config` command.

### `rdst config`

This is the primary way to manage your settings.

*   **Fetch config from AWS:**
    This command will interactively prompt you for an AWS Secrets Manager secret name and region. It will then fetch the secrets and save them to your `~/.rdstunnel_config.json` file.
    ```bash
    rdst config --fetch
    ```

*   **Show the current config:**
    ```bash
    rdst config --show
    ```

*   **Reset the config:**
    This will reset your `~/.rdstunnel_config.json` back to the original default values.
    ```bash
    rdst config --clean
    ```

### Example `defaults.json`

Your configuration file will need the following keys:
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
  "LOCAL_PORT": 3306
}
```


***

## 🚀 Usage

### `rdst start`
Starts the SSH tunnel as a background daemon process. It will use the configuration from `~/.rdstunnel_config.json` by default.
```bash
rdst start
```
After starting, the daemon's logs will be written to `~/.rdstunnel.log`.

You can also specify a custom configuration file for advanced use cases:
```bash
rdst start --config-file /path/to/another_config.json
```

### `rds-tunnel stop`
Finds the running daemon process and sends a signal to gracefully shut it down.
```bash
rds-tunnel stop
```

### `rdst status`
Checks if the tunnel is running and attempts to connect to the database to verify its status.
```bash
❯ rdst status
Tunnel: Active
Database: Connected
  - Bound to: 127.0.0.1:3306
```

### `rdst help`
Displays a list of all commands and their options.
```bash
rdst help
```

*** 

## 🤝 Contributing
Contributions are welcome! Please feel free to open issues or submit pull requests.
