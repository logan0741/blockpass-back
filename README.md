# blockpass-back

FastAPI backend for Blockpass. Includes MySQL connectivity and optional ngrok tunneling.

## Requirements
- Ubuntu 24.04 (tested)
- Python 3.12
- MySQL 8.0

## Project Structure
- `main.py`: FastAPI server with DB health check
- `ngrok_main.py`: Same server with ngrok tunnel
- `.venv/`: Python virtual environment

## Setup (First Time)
```bash
python3 -m venv /home/gunhee/blockpass-back/.venv
source /home/gunhee/blockpass-back/.venv/bin/activate
pip install fastapi uvicorn sqlalchemy pymysql pyngrok
```

## Database Setup (MySQL)
Create DB and user on the server:
```sql
CREATE DATABASE blockpass;
CREATE USER 'appuser'@'localhost' IDENTIFIED BY '2week';
GRANT ALL PRIVILEGES ON blockpass.* TO 'appuser'@'localhost';
FLUSH PRIVILEGES;
```

If you need remote access (Workbench), also create:
```sql
CREATE USER 'appuser'@'YOUR_PC_PUBLIC_IP' IDENTIFIED BY '2week';
GRANT ALL PRIVILEGES ON blockpass.* TO 'appuser'@'YOUR_PC_PUBLIC_IP';
FLUSH PRIVILEGES;
```

## Environment Variables
```bash
export DATABASE_URL="mysql+pymysql://appuser:2week@127.0.0.1:3306/blockpass"
```

If using ngrok:
```bash
export NGROK_AUTHTOKEN="YOUR_TOKEN"
```

## Run Server
Local server:
```bash
source /home/gunhee/blockpass-back/.venv/bin/activate
export DATABASE_URL="mysql+pymysql://appuser:2week@127.0.0.1:3306/blockpass"
python /home/gunhee/blockpass-back/main.py
```

ngrok server (if outbound 443 is allowed):
```bash
source /home/gunhee/blockpass-back/.venv/bin/activate
export DATABASE_URL="mysql+pymysql://appuser:2week@127.0.0.1:3306/blockpass"
export NGROK_AUTHTOKEN="YOUR_TOKEN"
python /home/gunhee/blockpass-back/ngrok_main.py
```

## Health Check
- `GET /` -> `{ "status": "ok" }`
- `GET /db/health` -> `{ "db_ok": true }`

## Workbench Connection (SSH Tunnel)
If security groups cannot be edited, use SSH tunnel from your local PC.

Local PC:
```bash
ssh -L 8000:localhost:8000 root@172.10.5.40
```
Then open:
- `http://localhost:8000`

For MySQL Workbench over SSH:
- Connection Method: Standard TCP/IP over SSH
- SSH Hostname: `172.10.5.40`
- SSH Username: `root`
- MySQL Hostname: `127.0.0.1`
- MySQL Port: `3306`
- Username: `appuser`
- Password: `2week`
- Default Schema: `blockpass`

## Notes
- If ngrok fails with timeout, outbound 443 is blocked by network policy.
- If SSH reverse tunneling fails, `AllowTcpForwarding` must be enabled in `/etc/ssh/sshd_config`.

