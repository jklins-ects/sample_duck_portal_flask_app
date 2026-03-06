# Sample Duck Portal Flask App

**Note:** AI (ChatGPT) was used in collaboration during the development of this project.

This repository contains a sample **Flask + Socket.IO** application that demonstrates how to build an NFC-based "portal" system similar to the Skylanders portal concept.

Two NFC readers act as duck portals. When a duck with an NFC tag is placed on a reader:

1. The NFC tag is read
2. The tag’s NDEF records are parsed
3. The duck ID is extracted
4. The browser UI updates in real time
5. A 3D duck model renders in the portal using **Three.js**

When the tag is removed, the portal clears automatically.

The system is designed to support interactive experiences such as duck battles, registration systems, or collectible tracking.

## Features

### Real NFC Portal Support

The application polls connected **PC/SC NFC readers** and reads Type 2 tags (such as NTAG213/215/216).

Each tag is expected to contain NDEF records like this:

```json
[
    {
        "type": "url",
        "value": "https://duckland-production.up.railway.app/ducks/69a8ea5053e250fdaf139d5a"
    },
    { "type": "text", "lang": "en", "value": "69a8ea5053e250fdaf139d5a" },
    {
        "type": "json",
        "value": {
            "_id": "69a8ea5053e250fdaf139d5a",
            "assembler": "Isaac Turner",
            "name": "Nimbus"
        }
    }
]
```

The system can use the JSON record as the preferred source for duck data and identifiers.

### Real-Time Web Updates

The app uses **Flask-SocketIO** so the browser updates instantly when:

- a duck is placed on a portal
- a duck is removed
- the portal state changes

The browser never needs to refresh.

### 3D Duck Rendering

Each portal renders a duck using **Three.js**.

The duck model is loaded dynamically and colored according to the duck data.

The page can also display:

- assembler
- duck name
- adjectives
- biography
- stats

## Simulator Mode

Developing NFC hardware interactions can be difficult without physical readers attached.

To make development easier, this project includes a **keyboard-driven simulator**.

When simulation mode is enabled:

- no NFC readers are required
- portal states can be controlled from the terminal
- the rest of the system behaves exactly the same

This allows you to test:

- UI updates
- socket events
- duck loading
- portal clearing
- 3D rendering

without needing hardware.

### Simulator Controls

```text
LEFT PORTAL
1 = PIXEL
2 = GLOW
3 = SPARK
4 = BUBBLE
5 = DERPY
c = clear left

RIGHT PORTAL
7 = PIXEL
8 = GLOW
9 = SPARK
0 = BUBBLE
- = DERPY
m = clear right

GENERAL
p = print current portal states
q = quit simulator input loop
```

Example:

```text
sim> 1
```

Places the **PIXEL** duck on the left portal.

## Project Structure

```text
duck_portal_app
│
├── app.py
├── nfc_portal.py
│
├── templates
│   └── index.html
│
├── static
│   ├── js
│   │   ├── portal_ui.js
│   │   └── duck_viewer.js
│   │
│   ├── models
│   │   ├── duck.obj
│   │   └── duck.mtl
│   │
│   └── images
│       └── Loading_Duck 1.gif
```

## Requirements

Python 3.9+ is recommended.

Install dependencies:

```bash
pip install flask flask-socketio pyscard
```

Optional but recommended for better socket performance:

```bash
pip install eventlet
```

## Running the App

### 1. Clone the repository

```bash
git clone https://github.com/jklins-ects/sample_duck_portal_flask_app.git
cd sample_duck_portal_flask_app
```

### 2. Create a virtual environment

Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

Mac/Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

or manually:

```bash
pip install flask flask-socketio pyscard
```

### 4. Start the server

```bash
python app.py
```

You should see output similar to:

```text
Flask server running at http://localhost:5000
Simulation mode is ON
```

### 5. Open the portal UI

Navigate to:

```text
http://localhost:5000
```

## Switching Between Simulator and Real Portals

Inside **app.py**:

```python
SIMULATION_MODE = True
```

### Simulator Mode

```python
SIMULATION_MODE = True
```

Uses keyboard controls to simulate portal behavior.

### Real Hardware Mode

```python
SIMULATION_MODE = False
```

Uses connected NFC readers.

## NFC Reader Notes

This project expects **PC/SC compatible readers**, such as:

- ACR122U
- PN532 readers configured for PC/SC

Each reader becomes a portal.

Reader names determine portal sides. For example:

```text
ACS ACR122U PICC Interface 0 → left portal
ACS ACR122U PICC Interface 1 → right portal
```

## Future Expansion Ideas

This project is intentionally simple and designed as a foundation for larger systems.

Possible extensions include:

- Duck battle mechanics
- Leaderboards
- Duck training stats
- Web-based duck registration
- Multiplayer portal systems
- Duck trading systems

## License

This project is intended as an educational example demonstrating:

- Flask
- WebSockets
- NFC hardware integration
- Real-time browser updates
- Three.js model rendering

Feel free to modify and expand it for your own projects.
