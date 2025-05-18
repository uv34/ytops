# Audio Streaming & Recommendation Application

## Overview

This Python-based application provides a secure, end-to-end audio streaming solution with both client and server components, featuring:

* **Encrypted Communication** using Diffie‑Hellman key exchange and AES encryption
* **Ogg Audio Handling** with page‑level granule position parsing
* **Real‑time Playback** via a GUI client built on CustomTkinter and Pygame
* **Recommendation Engine** powered by collaborative filtering (scikit‑learn)
* **Neural Network Analysis** for audio features using TensorFlow and librosa
* **MySQL Metadata Storage** with user authentication (bcrypt) and JWT tokens
* **Web Server** for managing content and streaming over HTTP
* **FFmpeg Auto‑Installer** for on‑the‑fly audio conversion
* **Email Notifications** via SMTP (MailManager)

## Prerequisites

* **Python 3.8+**
* **FFmpeg** (system path or installed via `ensure_ffmpeg.py`)
* **MySQL Server**
* **Gmail Account** (for SMTP email notifications)

## Installation

1. Clone the repository:

   ```bash
   git clone <repo-url>
   cd <repo-directory>
   ```
2. Install Python dependencies:

   ```bash
   pip install -r requirements.txt
   ```
3. (Optional) Install FFmpeg automatically:

   ```bash
   python ensure_ffmpeg.py
   ```
4. Configure database connection in `mysql_helper.py` or via environment variables:

   ```bash
   export DB_HOST=localhost
   export DB_USER=your_user
   export DB_PASS=your_password
   export DB_NAME=your_db
   ```
5. Configure JWT secret and SMTP credentials:

   ```bash
   export JWT_SECRET=your_jwt_secret
   export SMTP_USER=your_email@gmail.com
   export SMTP_PASS=your_smtp_password
   ```

## Usage

### Start Servers

```bash
python audio_server_v2.py      # Secure audio streaming server
python web_server.py           # HTTP content server
python general_server.py       # Token verification and support services
```

### Run Client

```bash
python client_ui_3.py          # Launch GUI client for streaming and playback
```

### Utilities

* **Recommendations**: `python recommendations.py`
* **Neural Network Analysis**: `python neural_networks.py`, `python network_with_tensor.py`

## Project Structure

```
├── admin_stuff.py        # Album creation and AI‑powered cover generation
├── audio_client_v2.py    # Socket client with playback queue
├── audio_server_v2.py    # Encrypted audio streaming server
├── checker.py            # Input validation utilities
├── client.py             # Core client logic and controllers
├── client_ui_3.py        # CustomTkinter GUI
├── custom_widgets.py     # Reusable Tkinter/CustomTkinter widgets
├── encryption.py         # Diffie‑Hellman & AES routines
├── ensure_ffmpeg.py      # Download/install FFmpeg if missing
├── general_client.py     # Shared client helper functions
├── general_server.py     # Shared server helper functions
├── mysql_helper.py       # Database controller with bcrypt & pandas support
├── network_with_tensor.py# TensorFlow Keras audio model training
├── neural_networks.py    # Audio feature extraction & NN demo
├── ogg_handler.py        # Ogg file low‑level parsing
├── protocol.py           # Message framing and parsing
├── recommendations.py    # Collaborative filtering engine
├── song.py               # Song metadata & playback segment model
├── web_server.py         # HTTP file/server streaming interface
└── MailManager.py        # SMTP email sending class
```

