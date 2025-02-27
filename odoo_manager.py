import sys
import os
import subprocess
import json
import webbrowser

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton,
                             QLabel, QLineEdit, QFileDialog, QMessageBox, QTextEdit, QComboBox, QDialog, QFormLayout)
from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot, QProcess

import psutil
import time
import platform

CONFIG_FILE = resource_path("config.json")
DOCKER_TEMPLATE = resource_path("docker-compose-template.yml")
DOCKER_COMPOSE_FILE = resource_path("docker-compose.yml")
ODOO_CONF_SAMPLE = resource_path("odoo.conf.sample")
ODOO_VERSIONS = ["16.0", "17.0", "18.0"]
ODOO_FLAVORS = ["Community", "Enterprise"]


def is_docker_running():
    """Check if the Docker daemon is running"""
    try:
        process = subprocess.run(["docker", "info"], capture_output=True, text=True)
        return process.returncode == 0
    except FileNotFoundError:
        return False


def start_docker_desktop():
    """Start Docker Desktop if it is not running (Windows & macOS)"""
    system = platform.system()

    if system == "Windows":
        # Check if Docker Desktop is already running
        for proc in psutil.process_iter(attrs=["name"]):
            if "Docker Desktop.exe" in proc.info["name"]:
                return True  # Docker is already running

        # Start Docker Desktop on Windows
        docker_path = r"C:\Program Files\Docker\Docker\Docker Desktop.exe"
        if os.path.exists(docker_path):
            subprocess.Popen(docker_path, shell=True)
            return True

    elif system == "Darwin":  # macOS
        # Check if Docker is already running
        for proc in psutil.process_iter(attrs=["name"]):
            if "Docker" in proc.info["name"]:  # Docker Desktop process
                return True

        # Start Docker Desktop on macOS
        subprocess.Popen(["open", "-a", "Docker"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    return False

def resource_path(relative_path):
    """Get the absolute path to a resource, works for dev and for PyInstaller."""
    try:
        # PyInstaller creates a temp folder and stores the path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)



class DockerComposeLogsThread(QThread):
    log_output = pyqtSignal(str)

    def __init__(self, cwd, parent=None):
        super().__init__(parent)
        self.cwd = cwd
        self.process = None
        self._running = True

    def run(self):
        try:
            # Startet docker-compose logs im Follow-Modus
            self.process = subprocess.Popen(
                ["docker-compose", "logs", "-f"],
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=(sys.platform == "win32")
            )
            while self._running:
                line = self.process.stdout.readline()
                if not line:
                    break
                self.log_output.emit(line.strip())
            # Schließe die Streams
            self.process.stdout.close()
            self.process.stderr.close()
            self.process.wait()
        except Exception as e:
            self.log_output.emit(f"Error: {str(e)}")

    def stop(self):
        self._running = False
        if self.process:
            self.process.terminate()


class DockerLogsDialog(QDialog):
    def __init__(self, cwd, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Odoo Log")
        self.resize(600, 400)

        layout = QVBoxLayout(self)
        self.text_edit = QTextEdit(self)
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)

        # QProcess initialisieren und konfigurieren
        self.process = QProcess(self)
        self.process.setProgram("docker-compose")
        self.process.setArguments(["logs", "-f"])
        self.process.setWorkingDirectory(cwd)

        # Verbinde die Ready-Signale mit den Handlern
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)

        # Starte den Log-Prozess
        self.process.start()

    def handle_stdout(self):
        data = self.process.readAllStandardOutput()
        text = bytes(data).decode("utf-8")
        self.text_edit.append(text)

    def handle_stderr(self):
        data = self.process.readAllStandardError()
        text = bytes(data).decode("utf-8")
        self.text_edit.append(text)

    def closeEvent(self, event):
        if self.process.state() == QProcess.ProcessState.Running:
            self.process.terminate()
            self.process.waitForFinished(3000)
        event.accept()

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
                self.log_output.emit(f"Error: Cant find docker-compose file: {compose_file}")
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
            self.log_output.emit("Error: Docker Compose not found! Make sure, docker is installed and running")
        except Exception as e:
            self.log_output.emit(f"Error: {str(e)}")


def find_odoo_addons_paths(base_path):
    addons_paths = set()  # Use a set to avoid duplicate paths
    for root, dirs, files in os.walk(base_path):
        # Check if the directory contains both __init__.py and __manifest__.py
        if "__init__.py" in files and "__manifest__.py" in files:
            # Add the parent directory as an addons path
            addons_paths.add(os.path.dirname(root))
    return list(addons_paths)  # Convert the set to a list


class OdooManagerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.odoo_running = False
        self.initUI()
        self.load_config()

        # Check if Docker is running
        if not self.ensure_docker_running():
            QMessageBox.critical(self, "Docker Error", "Docker is not running and could not be started!")
            sys.exit(1)  # Exit the app if Docker is not running



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
        self.browse_button = QPushButton("Select Odoo Addons path", self)
        self.browse_button.clicked.connect(self.select_repo_path)
        layout.addWidget(QLabel("Local Odoo addons path:"))
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

        self.connect_button = QPushButton("Connect", self)
        self.connect_button.clicked.connect(self.open_browser)
        self.connect_button.setEnabled(False)
        layout.addWidget(self.connect_button)

        self.odoo_log_button = QPushButton("Odoo Log", self)
        self.odoo_log_button.clicked.connect(self.show_odoo_log)
        self.odoo_log_button.setEnabled(False)
        layout.addWidget(self.odoo_log_button)

        self.save_button = QPushButton("Save", self)
        self.save_button.clicked.connect(self.save_config)
        layout.addWidget(self.save_button)

        self.log_window = QTextEdit(self)
        self.log_window.setReadOnly(True)
        layout.addWidget(QLabel("Logs:"))
        layout.addWidget(self.log_window)

        self.setLayout(layout)
        self.setWindowTitle("OPaaS Odoo Manager")
        self.setWindowIcon(QIcon(resource_path("icon.png")))
        self.resize(1000, 700)

    def show_odoo_log(self):
        """
        Öffnet einen neuen Dialog, der den docker-compose Logstream (Odoo Logs) anzeigt.
        """
        self.log_dialog = DockerLogsDialog(os.getcwd(), self)
        self.log_dialog.show()

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
            QMessageBox.information(self, "Success", "Login Successful")
        else:
            QMessageBox.critical(self, "Error", f"Docker Login failed: {process.stderr}")

    def select_repo_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose Odoo Addons path")
        if folder:
            self.repo_path.setText(folder)
            self.log(f"Addons path set: {folder}")

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
        self.log("Configuration saved")
        QMessageBox.information(self, "saved", "Configuration saved!")

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
            self.log("Configuration file not found, new one will be created.")
            self.save_config()

    def generate_odoo_conf(self, addons_paths):
        # Define the paths for the sample and final configuration files
        sample_conf_path = resource_path("odoo.conf.sample")
        final_conf_path = os.path.join(os.getcwd(), "odoo.conf")

        # Check if the sample configuration file exists
        if not os.path.exists(sample_conf_path):
            self.log("Error: Sample configuration file (odoo.conf.sample) not found!")
            return None

        # Read the sample configuration file
        with open(sample_conf_path, "r") as f:
            sample_content = f.read()

        # Konvertiere den in der UI angegebenen Pfad in ein Unix-Format
        clean_repo_path = self.repo_path.text().replace("\\", "/")

        container_addons_paths = []
        for path in addons_paths:
            # Ersetze auch hier Backslashes durch Schrägstriche
            clean_path = path.replace("\\", "/")
            if clean_path.startswith(clean_repo_path):  # Check if the path is under the repo directory
                # Replace the host repo path with the container mount path
                container_path = clean_path.replace(clean_repo_path, "/mnt/extra-addons")
                container_addons_paths.append(container_path)
            else:
                # If it's not under the repo directory, keep it as is (e.g., default paths)
                container_addons_paths.append(clean_path)

        # Join the container paths into a comma-separated string
        addons_paths_str = ",".join(container_addons_paths)

        # Replace the placeholder with the container addons paths
        final_content = sample_content.replace("{{ADDONS_PATH}}", addons_paths_str)

        # Write the final configuration to odoo.conf
        with open(final_conf_path, "w") as f:
            f.write(final_content)

        # Log the creation of the odoo.conf file
        self.log(f"Odoo configuration file created: {final_conf_path}")
        return final_conf_path

    def ensure_docker_running(self):
        """Ensure that Docker is running, and start it if necessary"""
        if not is_docker_running():
            self.log("Docker is not running, attempting to start...")
            if start_docker_desktop():
                self.log("Docker Desktop started. Waiting for initialization...")
                for _ in range(30):  # Wait up to 30 seconds
                    if is_docker_running():
                        self.log("Docker is now ready.")
                        return True
                    time.sleep(2)
                self.log("Docker could not be started. Please check manually.")
            else:
                self.log("Could not find Docker Desktop. Is it installed?")
        return is_docker_running()

    def generate_docker_compose(self):
        # Get the repository path from the UI
        repo_path = self.repo_path.text()
        compose_path = os.path.join(os.getcwd(), DOCKER_COMPOSE_FILE)

        # Check if the Docker template exists
        if not os.path.exists(DOCKER_TEMPLATE):
            self.log("Error: Docker Compose template not found!")
            return

        # Read the Docker template content
        with open(DOCKER_TEMPLATE, "r") as f:
            template_content = f.read()

        # Determine the Odoo image based on the selected flavor
        if self.odoo_flavor.currentText() == "Enterprise":
            odoo_image = f"{self.docker_repo.text()}:{self.docker_tag.text()}"
        else:
            odoo_image = f"odoo:{self.odoo_version.currentText()}"

        # Find all Odoo addons paths
        addons_paths = find_odoo_addons_paths(repo_path)
        addons_paths.append("/mnt/extra-addons")  # Add the default addons path

        # Generate the odoo.conf file
        conf_path = self.generate_odoo_conf(addons_paths)
        if not conf_path:
            return  # Stop if the configuration file could not be generated

        # Replace placeholders in the Docker template
        docker_compose_content = template_content.replace("{{ODOO_IMAGE}}", odoo_image)
        docker_compose_content = docker_compose_content.replace("{{REPO_PATH}}", repo_path)
        docker_compose_content = docker_compose_content.replace("{{ODOO_CONF_PATH}}", os.path.abspath(conf_path))

        # Write the final Docker Compose file
        with open(compose_path, "w") as f:
            f.write(docker_compose_content)

        # Log the creation of the Docker Compose file
        self.log(f"Docker Compose file created with Odoo image: {odoo_image}")

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
            self.odoo_log_button.setEnabled(True)

    def stop_docker(self):
        self.docker_thread = DockerComposeThread(["docker-compose", "down"], cwd=os.getcwd())
        self.docker_thread.log_output.connect(self.log)
        self.docker_thread.start()
        self.stop_button.setEnabled(False)
        self.reset_button.setEnabled(False)
        self.connect_button.setEnabled(False)
        self.odoo_log_button.setEnabled(False)

    def reset_docker(self):
        self.docker_thread = DockerComposeThread(["docker-compose", "down", "-v"], cwd=os.getcwd())
        self.docker_thread.log_output.connect(self.log)
        self.docker_thread.start()
        self.reset_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.connect_button.setEnabled(False)
        self.odoo_log_button.setEnabled(False)

    def open_browser(self):
        webbrowser.open("http://localhost:8069")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = OdooManagerApp()
    ex.show()
    sys.exit(app.exec())
