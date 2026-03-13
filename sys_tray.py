import sys
import os
import subprocess
import signal
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import QTimer

class SystemServiceTray:
    def __init__(self):
        # Force flush stdout/stderr
        import sys
        sys.stdout.reconfigure(line_buffering=True)
        
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        # Ensure we are in the project root
        self.project_root = os.path.dirname(os.path.abspath(__file__))
        os.chdir(self.project_root)

        # Create the icon
        icon_path = os.path.join(self.project_root, "sys_core/icon.ico")
        if os.path.exists(icon_path):
            print(f"Loading icon from {icon_path}", flush=True)
            self.icon = QIcon(icon_path)
        else:
            # Fallback: Create a larger, highly visible icon
            from PyQt6.QtGui import QPixmap, QPainter, QColor, QBrush, QPen
            print("Creating fallback high-visibility icon", flush=True)
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor("transparent"))
            painter = QPainter(pixmap)
            # Draw a white circle with a magenta border
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QBrush(QColor("white")))
            painter.setPen(QPen(QColor("magenta"), 3))
            painter.drawEllipse(2, 2, 28, 28)
            painter.end()
            self.icon = QIcon(pixmap)

        # Create the tray icon
        self.tray = QSystemTrayIcon(self.icon, self.app)
        if not self.tray.isSystemTrayAvailable():
            print("CRITICAL: System tray is NOT available on this system!", flush=True)
        
        self.tray.setToolTip("System Service")

        # Create the menu
        self.menu = QMenu()
        
        self.status_action = QAction("Status: Checking...")
        self.status_action.setEnabled(False)
        self.menu.addAction(self.status_action)
        
        self.menu.addSeparator()

        self.start_action = QAction("Start Service")
        self.start_action.triggered.connect(self.start_service)
        self.menu.addAction(self.start_action)

        self.stop_action = QAction("Stop Service")
        self.stop_action.triggered.connect(self.stop_service)
        self.menu.addAction(self.stop_action)

        self.menu.addSeparator()

        self.quit_action = QAction("Quit Utility")
        self.quit_action.triggered.connect(self.quit_app)
        self.menu.addAction(self.quit_action)

        # Set the menu to the tray
        self.tray.setContextMenu(self.menu)
        self.tray.show()

        # Timer to check status periodically
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_status)
        self.timer.start(3000)  # Every 3 seconds
        self.check_status()

    def check_status(self):
        try:
            # Check if engine is running
            output = subprocess.check_output(["ps", "aux"]).decode()
            is_running = "sys_core.engine" in output
            
            if is_running:
                self.status_action.setText("Status: ACTIVE")
                self.start_action.setEnabled(False)
                self.stop_action.setEnabled(True)
            else:
                self.status_action.setText("Status: INACTIVE")
                self.start_action.setEnabled(True)
                self.stop_action.setEnabled(False)
        except Exception:
            self.status_action.setText("Status: Error")

    def start_service(self):
        subprocess.Popen(["./run_sys.sh"], cwd=self.project_root)
        QTimer.singleShot(1000, self.check_status)

    def stop_service(self):
        subprocess.Popen(["./stop_sys.sh"], cwd=self.project_root)
        QTimer.singleShot(1000, self.check_status)

    def quit_app(self):
        self.app.quit()

    def run(self):
        sys.exit(self.app.exec())

if __name__ == "__main__":
    tray = SystemServiceTray()
    tray.run()
