import sys
import os
import subprocess
import json
import webbrowser
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton,
                             QLabel, QLineEdit, QFileDialog, QMessageBox, QTextEdit, QComboBox)
from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot

CONFIG_FILE = "config.json"
DOCKER_TEMPLATE = "docker-compose-template.yml"
DOCKER_COMPOSE_FILE = "docker-compose.yml"
ODOO_VERSIONS = ["16.0", "17.0", "18.0"]


class DockerComposeThread(QThread):
    log_output = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)

    def __init__(self, command, cwd):
        super().__init__()
        self.command = command
        self.cwd = cwd

    def run(self):
        try:
            compose_file = os.path.join(os.getcwd(), DOCKER_COMPOSE_FILE)
            if not os.path.exists(compose_file):
                self.log_output.emit(f"Fehler: Docker-Compose Datei nicht gefunden: {compose_file}")
                return

            process = subprocess.Popen(self.command, cwd=os.getcwd(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, shell=(sys.platform == "win32"))
            for line in process.stdout:
                self.log_output.emit(line.strip())
            for line in process.stderr:
                self.log_output.emit(line.strip())
            process.wait()
            self.finished_signal.emit(process.returncode == 0)
        except FileNotFoundError:
            self.log_output.emit("Fehler: Docker Compose nicht gefunden! Stelle sicher, dass Docker installiert ist.")
        except Exception as e:
            self.log_output.emit(f"Fehler: {str(e)}")


class OdooManagerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.odoo_running = False
        self.initUI()
        self.load_config()

    def initUI(self):
        layout = QVBoxLayout()

        self.docker_user = QLineEdit(self)
        self.docker_key = QLineEdit(self)
        self.docker_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(QLabel("Docker Hub Username:"))
        layout.addWidget(self.docker_user)
        layout.addWidget(QLabel("Docker Hub API Key:"))
        layout.addWidget(self.docker_key)

        self.odoo_version = QComboBox(self)
        self.odoo_version.addItems(ODOO_VERSIONS)
        layout.addWidget(QLabel("Odoo Version:"))
        layout.addWidget(self.odoo_version)

        self.repo_path = QLineEdit(self)
        self.browse_button = QPushButton("Repository Pfad auswählen", self)
        self.browse_button.clicked.connect(self.select_repo_path)
        layout.addWidget(QLabel("Lokaler Repository-Pfad:"))
        layout.addWidget(self.repo_path)
        layout.addWidget(self.browse_button)

        self.start_button = QPushButton("Start Odoo", self)
        self.start_button.clicked.connect(self.start_docker)
        layout.addWidget(self.start_button)

        self.stop_button = QPushButton("Stop Odoo", self)
        self.stop_button.clicked.connect(self.stop_docker)
        self.stop_button.setEnabled(False)
        layout.addWidget(self.stop_button)

        self.connect_button = QPushButton("Verbinden", self)
        self.connect_button.clicked.connect(self.open_browser)
        self.connect_button.setEnabled(False)
        layout.addWidget(self.connect_button)

        self.save_button = QPushButton("Speichern", self)
        self.save_button.clicked.connect(self.save_config)
        layout.addWidget(self.save_button)

        self.log_window = QTextEdit(self)
        self.log_window.setReadOnly(True)
        layout.addWidget(QLabel("Logs:"))
        layout.addWidget(self.log_window)

        self.setLayout(layout)
        self.setWindowTitle("Odoo Manager")
        self.resize(1000, 700)

    def log(self, message):
        self.log_window.append(message)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                self.docker_user.setText(config.get("docker_user", ""))
                self.docker_key.setText(config.get("docker_key", ""))
                self.repo_path.setText(config.get("repo_path", ""))
                self.odoo_version.setCurrentText(config.get("odoo_version", "17.0"))
        else:
            self.log("Konfigurationsdatei nicht gefunden, eine neue wird erstellt.")
            self.save_config()

    def save_config(self):
        config = {
            "docker_user": self.docker_user.text(),
            "docker_key": self.docker_key.text(),
            "repo_path": self.repo_path.text(),
            "odoo_version": self.odoo_version.currentText()
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f)
        self.log("Konfiguration gespeichert!")
        QMessageBox.information(self, "Gespeichert", "Konfiguration gespeichert!")

    def generate_docker_compose(self):
        odoo_version = self.odoo_version.currentText()
        repo_path = self.repo_path.text()
        compose_path = os.path.join(os.getcwd(), DOCKER_COMPOSE_FILE)

        if not os.path.exists(DOCKER_TEMPLATE):
            self.log("Fehler: Docker-Compose Template nicht gefunden!")
            return

        with open(DOCKER_TEMPLATE, "r") as f:
            template_content = f.read()

        docker_compose_content = template_content.replace("{{ODOO_VERSION}}", odoo_version)
        docker_compose_content = docker_compose_content.replace("{{REPO_PATH}}", repo_path)

        with open(compose_path, "w") as f:
            f.write(docker_compose_content)

        self.log(f"Docker-Compose Datei mit Odoo Version {odoo_version} und Repository-Pfad {repo_path} erstellt.")

    def start_docker(self):
        self.generate_docker_compose()
        self.docker_thread = DockerComposeThread(["docker-compose", "up", "-d"], cwd=os.getcwd())
        self.docker_thread.log_output.connect(self.log)
        self.docker_thread.finished_signal.connect(self.enable_buttons)
        self.docker_thread.start()

    @pyqtSlot(bool)
    def enable_buttons(self, success):
        if success:
            self.odoo_running = True
            self.stop_button.setEnabled(True)
            self.connect_button.setEnabled(True)

    def stop_docker(self):
        self.docker_thread = DockerComposeThread(["docker-compose", "down", "--volumes"], cwd=os.getcwd())
        self.docker_thread.log_output.connect(self.log)
        self.docker_thread.start()
        self.stop_button.setEnabled(False)
        self.connect_button.setEnabled(False)

    def select_repo_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Wähle Repository-Pfad")
        if folder:
            self.repo_path.setText(folder)
            self.log(f"Repository Pfad gesetzt: {folder}")

    def open_browser(self):
        webbrowser.open("http://localhost:8069")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = OdooManagerApp()
    ex.show()
    sys.exit(app.exec())
