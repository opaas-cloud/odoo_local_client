# OPaaS Odoo Manager

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![PyQt6](https://img.shields.io/badge/PyQt6-6.0%2B-green)
![Docker](https://img.shields.io/badge/Docker-20.10%2B-orange)
![Odoo](https://img.shields.io/badge/Odoo-16.0%2B-brightgreen)

**OPaaS Odoo Manager** is a user-friendly application for managing Odoo instances using Docker. The application allows you to start, stop, and reset Odoo containers, as well as automatically detect addons paths and integrate them into the Odoo configuration.

## Features

- **Odoo Versions**: Support for Odoo Community and Enterprise Editions (Versions 16.0, 17.0, 18.0).
- **Docker Integration**: Start, stop, and reset Odoo containers.
- **Automatic Addons Detection**: Recursively search for Odoo modules in a specified directory.
- **Configuration File**: Dynamically generate the `odoo.conf` file with the correct addons paths.
- **Cross-Platform**: Works on both Windows and Linux.

## Prerequisites

- **Python 3.8+**
- **Docker** and **Docker Compose**
- **PyQt6** (for the GUI)

## Installation

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/your-username/opaas-odoo-manager.git
   cd opaas-odoo-manager
