import unittest
import uuid

from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication

from clipboard_app.app import SingleInstanceGuard


class SingleInstanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_second_instance_notifies_primary_instead_of_starting(self):
        server_name = "Clipboard.Test." + uuid.uuid4().hex
        primary = SingleInstanceGuard(server_name)
        activations = []
        primary.activate_requested.connect(lambda: activations.append(True))
        secondary = SingleInstanceGuard(server_name)
        self.app.processEvents()
        try:
            self.assertTrue(primary.is_primary)
            self.assertFalse(secondary.is_primary)
            self.assertEqual([True], activations)
        finally:
            if primary.server is not None:
                primary.server.close()
            QLocalServer.removeServer(server_name)


if __name__ == "__main__":
    unittest.main()
