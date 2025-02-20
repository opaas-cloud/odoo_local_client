import sys
import os
import subprocess
import json
import webbrowser
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton,
                             QLabel, QLineEdit, QFileDialog, QMessageBox, QTextEdit, QComboBox, QDialog, QFormLayout)
from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot

CONFIG_FILE = "config.json"
DOCKER_TEMPLATE = "docker-compose-template.yml"
DOCKER_COMPOSE_FILE = "docker-compose.yml"
ODOO_VERSIONS = ["16.0", "17.0", "18.0"]
ODOO_FLAVORS = ["Community", "Enterprise"]


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

        self.odoo_flavor = QComboBox(self)
        self.odoo_flavor.addItems(ODOO_FLAVORS)
        self.odoo_flavor.currentIndexChanged.connect(self.toggle_enterprise_fields)
        layout.addWidget(QLabel("Odoo Edition:"))
        layout.addWidget(self.odoo_flavor)

        self.odoo_version = QComboBox(self)
        self.odoo_version.addItems(ODOO_VERSIONS)
        layout.addWidget(QLabel("Odoo Version:"))
        layout.addWidget(self.odoo_version)

        self.docker_user = QLineEdit(self)
        self.docker_key = QLineEdit(self)
        self.docker_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.docker_repo = QLineEdit(self)
        self.docker_tag = QLineEdit(self)
        self.login_button = QPushButton("Docker Login")
        self.login_button.clicked.connect(self.docker_login)

        self.enterprise_fields = [
            QLabel("Docker Hub Username:"), self.docker_user,
            QLabel("Docker Hub API Key:"), self.docker_key,
            QLabel("Docker Repository:"), self.docker_repo,
            QLabel("Docker Image Tag:"), self.docker_tag,
            self.login_button
        ]

        for widget in self.enterprise_fields:
            layout.addWidget(widget)
            widget.setVisible(False)

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

        self.reset_button = QPushButton("Reset Odoo", self)
        self.reset_button.clicked.connect(self.reset_docker)
        self.reset_button.setEnabled(False)
        layout.addWidget(self.reset_button)

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
        self.setWindowTitle("OPaaS Odoo Manager")
        self.resize(1000, 700)

    def toggle_enterprise_fields(self):
        is_enterprise = self.odoo_flavor.currentText() == "Enterprise"
        for widget in self.enterprise_fields:
            widget.setVisible(is_enterprise)
        self.odoo_version.setVisible(not is_enterprise)

    def log(self, message):
        self.log_window.append(message)

    def docker_login(self):
        username = self.docker_user.text()
        password = self.docker_key.text()

        process = subprocess.run(["docker", "login", "--username", username, "--password", password],
                                 capture_output=True, text=True)
        if process.returncode == 0:
            QMessageBox.information(self, "Erfolg", "Docker Login erfolgreich!")
        else:
            QMessageBox.critical(self, "Fehler", f"Docker Login fehlgeschlagen: {process.stderr}")

    def select_repo_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Wähle Repository-Pfad")
        if folder:
            self.repo_path.setText(folder)
            self.log(f"Repository Pfad gesetzt: {folder}")

    def save_config(self):
        config = {
            "repo_path": self.repo_path.text(),
            "odoo_flavor": self.odoo_flavor.currentText(),
            "docker_user": self.docker_user.text(),
            "docker_key": self.docker_key.text(),
            "docker_repo": self.docker_repo.text(),
            "docker_tag": self.docker_tag.text()
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f)
        self.log("Konfiguration gespeichert!")
        QMessageBox.information(self, "Gespeichert", "Konfiguration gespeichert!")

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                self.repo_path.setText(config.get("repo_path", ""))
                self.odoo_flavor.setCurrentText(config.get("odoo_flavor", "Community"))
                self.docker_user.setText(config.get("docker_user", ""))
                self.docker_key.setText(config.get("docker_key", ""))
                self.docker_repo.setText(config.get("docker_repo", ""))
                self.docker_tag.setText(config.get("docker_tag", ""))
        else:
            self.log("Konfigurationsdatei nicht gefunden, eine neue wird erstellt.")
            self.save_config()

    def generate_docker_compose(self):
        repo_path = self.repo_path.text()
        compose_path = os.path.join(os.getcwd(), DOCKER_COMPOSE_FILE)

        if not os.path.exists(DOCKER_TEMPLATE):
            self.log("Fehler: Docker-Compose Template nicht gefunden!")
            return

        with open(DOCKER_TEMPLATE, "r") as f:
            template_content = f.read()

        if self.odoo_flavor.currentText() == "Enterprise":
            odoo_image = f"{self.docker_repo.text()}:{self.docker_tag.text()}"
        else:
            odoo_image = f"odoo:{self.odoo_version.currentText()}"

        docker_compose_content = template_content.replace("{{ODOO_IMAGE}}", odoo_image)
        docker_compose_content = docker_compose_content.replace("{{REPO_PATH}}", repo_path)

        with open(compose_path, "w") as f:
            f.write(docker_compose_content)

        self.log(f"Docker-Compose Datei mit Odoo Image {odoo_image} erstellt.")

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
            self.reset_button.setEnabled(True)
            self.connect_button.setEnabled(True)

    def stop_docker(self):
        self.docker_thread = DockerComposeThread(["docker-compose", "down", "--volumes"], cwd=os.getcwd())
        self.docker_thread.log_output.connect(self.log)
        self.docker_thread.start()
        self.stop_button.setEnabled(False)
        self.reset_button.setEnabled(False)
        self.connect_button.setEnabled(False)

    def reset_docker(self):
        self.docker_thread = DockerComposeThread(["docker-compose", "down", "-v"], cwd=os.getcwd())
        self.docker_thread.log_output.connect(self.log)
        self.docker_thread.start()
        self.reset_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.connect_button.setEnabled(False)

    def open_browser(self):
        webbrowser.open("http://localhost:8069")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = OdooManagerApp()
    ex.show()
    sys.exit(app.exec())
