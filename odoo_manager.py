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
ODOO_VERSIONS = ["16.0", "17.0", "18.0"]


class DockerComposeThread(QThread):
    log_output = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)

    def __init__(self, command, cwd):
        super().__init__()
        self.command = command
        self.cwd = cwd

    def run(self):
        process = subprocess.Popen(self.command, cwd=self.cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True)
        for line in process.stdout:
            self.log_output.emit(line.strip())
        for line in process.stderr:
            self.log_output.emit(line.strip())
        process.wait()
        self.finished_signal.emit(True if process.returncode == 0 else False)


class OdooLogThread(QThread):
    log_output = pyqtSignal(str)

    def __init__(self, cwd):
        super().__init__()
        self.cwd = cwd
        self.running = True

    def run(self):
        process = subprocess.Popen(["docker-compose", "logs", "-f", "web"], cwd=self.cwd, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        while self.running:
            line = process.stdout.readline()
            if not line:
                break
            self.log_output.emit(line.strip())
        process.terminate()

    def stop(self):
        self.running = False


class OdooManagerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.odoo_running = False
        self.initUI()
        self.load_config()

    def initUI(self):
        layout = QVBoxLayout()

        # Docker Hub Credentials
        self.docker_user = QLineEdit(self)
        self.docker_key = QLineEdit(self)
        self.docker_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(QLabel("Docker Hub Username:"))
        layout.addWidget(self.docker_user)
        layout.addWidget(QLabel("Docker Hub API Key:"))
        layout.addWidget(self.docker_key)

        # Odoo Version Auswahl
        self.odoo_version = QComboBox(self)
        self.odoo_version.addItems(ODOO_VERSIONS)
        layout.addWidget(QLabel("Odoo Version:"))
        layout.addWidget(self.odoo_version)

        # Repository Pfad Auswahl
        self.repo_path = QLineEdit(self)
        self.browse_button = QPushButton("Repository Pfad auswählen", self)
        self.browse_button.clicked.connect(self.select_repo_path)
        layout.addWidget(QLabel("Lokaler Repository-Pfad:"))
        layout.addWidget(self.repo_path)
        layout.addWidget(self.browse_button)

        # Docker Compose Steuerung
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

        # Log Fenster
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

    def select_repo_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Wähle Repository-Pfad")
        if folder:
            self.repo_path.setText(folder)
            self.log(f"Repository Pfad gesetzt: {folder}")

    def start_docker(self):
        repo_path = self.repo_path.text()
        self.docker_thread = DockerComposeThread(["docker-compose", "up", "-d"], cwd=repo_path)
        self.docker_thread.log_output.connect(self.log)
        self.docker_thread.finished_signal.connect(self.enable_buttons)
        self.docker_thread.start()

    @pyqtSlot(bool)
    def enable_buttons(self, success):
        if success:
            self.odoo_running = True
            self.stop_button.setEnabled(True)
            self.connect_button.setEnabled(True)
            self.log_thread = OdooLogThread(cwd=self.repo_path.text())
            self.log_thread.log_output.connect(self.log)
            self.log_thread.start()

    def stop_docker(self):
        repo_path = self.repo_path.text()
        self.docker_thread = DockerComposeThread(["docker-compose", "down"], cwd=repo_path)
        self.docker_thread.log_output.connect(self.log)
        self.docker_thread.start()
        self.stop_button.setEnabled(False)
        self.connect_button.setEnabled(False)
        self.log_thread.stop()

    def open_browser(self):
        webbrowser.open("http://localhost:8069")

    def closeEvent(self, event):
        if self.odoo_running:
            self.stop_docker()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = OdooManagerApp()
    ex.show()
    sys.exit(app.exec())