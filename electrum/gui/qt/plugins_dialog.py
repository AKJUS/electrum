from typing import TYPE_CHECKING, Optional
from functools import partial
import shutil
import os

from PyQt6.QtWidgets import QLabel, QVBoxLayout, QGridLayout, QPushButton, QWidget, QScrollArea, QFormLayout, QFileDialog, QMenu, QApplication
from PyQt6.QtCore import Qt

from electrum.i18n import _

from .util import WindowModalDialog, Buttons, CloseButton, WWLabel, insert_spaces, MessageBoxMixin, EnterButton
from .util import read_QIcon_from_bytes, IconLabel


if TYPE_CHECKING:
    from . import ElectrumGui
    from electrum_cc import ECPrivkey
    from electrum.simple_config import SimpleConfig
    from electrum.plugin import Plugins


class PluginDialog(WindowModalDialog):

    def __init__(self, name, metadata, status_button: Optional['PluginStatusButton'], window: 'PluginsDialog'):
        display_name = metadata.get('fullname', '')
        author = metadata.get('author', '')
        description = metadata.get('description', '')
        requires = metadata.get('requires')
        version = metadata.get('version')
        zip_hash = metadata.get('zip_hash_sha256', None)
        icon_path = metadata.get('icon')

        WindowModalDialog.__init__(self, window, 'Plugin')
        self.setMinimumSize(400, 250)
        self.window = window
        self.metadata = metadata
        self.plugins = self.window.plugins
        self.name = name
        self.status_button = status_button
        p = self.plugins.get(name)  # is enabled
        vbox = QVBoxLayout(self)
        name_label = IconLabel(text=display_name, reverse=True)
        if icon_path:
            name_label.icon_size = 64
            icon = read_QIcon_from_bytes(self.plugins.read_file(name, icon_path))
            name_label.setIcon(icon)
        vbox.addWidget(name_label)
        form = QFormLayout(None)
        if author:
            form.addRow(QLabel(_('Author') + ':'), QLabel(author))
        if description:
            form.addRow(QLabel(_('Description') + ':'), WWLabel(description))
        if version:
            form.addRow(QLabel(_('Version') + ':'), QLabel(version))
        if zip_hash:
            form.addRow(QLabel('Hash [sha256]:'), WWLabel(insert_spaces(zip_hash, 8)))
        if requires:
            msg = '\n'.join(map(lambda x: x[1], requires))
            form.addRow(QLabel(_('Requires') + ':'), WWLabel(msg))
        vbox.addLayout(form)
        vbox.addStretch()
        close_button = CloseButton(self)
        close_button.setText(_('Close'))
        buttons = [close_button]
        if not self.plugins.is_installed(name):
            install_button = QPushButton(_('Install...'))
            install_button.clicked.connect(self.accept)
            buttons.insert(0, install_button)
        else:
            remove_button = QPushButton(_('Uninstall'))
            remove_button.clicked.connect(self.do_remove)
            buttons.insert(0, remove_button)
            if not self.plugins.is_authorized(name):
                auth_button = QPushButton(_('Authorize...'))
                auth_button.clicked.connect(self.do_authorize)
                buttons.insert(0, auth_button)
            elif not self.plugins.is_auto_loaded(name):
                toggle_button = QPushButton('')
                p = self.plugins.get(name)
                is_enabled = p and p.is_enabled()
                toggle_button.setText(_('Disable') if is_enabled else _('Enable'))
                toggle_button.clicked.connect(self.do_toggle)
                buttons.insert(0, toggle_button)
            # add settings button
            if p and p.requires_settings() and p.is_enabled():
                settings_button = EnterButton(
                    _('Settings'),
                    partial(p.settings_dialog, self))
                buttons.insert(1, settings_button)
        # add buttonss
        vbox.addLayout(Buttons(*buttons))

    def do_toggle(self):
        self.close()
        self.window.do_toggle(self.name, self.status_button)

    def do_remove(self):
        self.window.uninstall_plugin(self.name)
        self.close()

    def do_authorize(self):
        assert not self.plugins.is_authorized(self.name)
        privkey = self.window.get_plugins_privkey()
        if not privkey:
            return
        filename = self.plugins.zip_plugin_path(self.name)
        self.window.plugins.authorize_plugin(self.name, filename, privkey)
        if self.status_button:
            self.status_button.update()
        self.close()


class PluginStatusButton(QPushButton):

    def __init__(self, window: 'PluginsDialog', name: str):
        QPushButton.__init__(self, '')
        self.window = window
        self.plugins = window.plugins
        self.name = name
        self.clicked.connect(self.show_plugin_dialog)
        self.update()

    def show_plugin_dialog(self):
        metadata = self.plugins.descriptions[self.name]
        d = PluginDialog(self.name, metadata, self, self.window)
        d.exec()

    def update(self):
        from .util import ColorScheme
        p = self.plugins.get(self.name)
        plugin_is_loaded = p is not None
        enabled = (
            not plugin_is_loaded
            or plugin_is_loaded and p.can_user_disable()
        )
        self.setEnabled(enabled)
        if not self.window.plugins.is_authorized(self.name):
            text, color = _('Unauthorized'), ColorScheme.RED
        else:
            if self.window.plugins.is_auto_loaded(self.name):
                text, color = _('Auto-loaded'), ColorScheme.DEFAULT
            else:
                if p is not None and p.is_enabled():
                    text, color = _('Enabled'), ColorScheme.BLUE
                else:
                    text, color = _('Disabled'), ColorScheme.DEFAULT
        self.setStyleSheet(color.as_stylesheet())
        self.setText(text)


class PluginsDialog(WindowModalDialog, MessageBoxMixin):

    def __init__(self, config: 'SimpleConfig', plugins:'Plugins', *, gui_object: Optional['ElectrumGui'] = None):
        WindowModalDialog.__init__(self, None, _('Electrum Plugins'))
        self.gui_object = gui_object
        self.config = config
        self.plugins = plugins
        vbox = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setEnabled(True)
        scroll.setWidgetResizable(True)
        scroll.setMinimumSize(400, 250)
        scroll_w = QWidget()
        scroll.setWidget(scroll_w)
        self.grid = QGridLayout()
        self.grid.setColumnStretch(0, 1)
        scroll_w.setLayout(self.grid)
        vbox.addWidget(scroll)
        add_button = QPushButton(_('Add'))
        menu = QMenu()
        for name, item in self.plugins.internal_plugin_metadata.items():
            fullname = item['fullname']
            if not fullname:
                continue
            if self.plugins.is_auto_loaded(name):
                continue
            menu.addAction(fullname, partial(self.add_internal_plugin, name))
        menu.addSeparator()
        m3 = menu.addMenu('Third-party plugin')
        m3.addAction(_('Local ZIP file'), self.add_plugin_dialog)
        m3.addAction(_('Download ZIP file'), self.download_plugin_dialog)
        add_button.setMenu(menu)
        vbox.addLayout(Buttons(add_button, CloseButton(self)))
        self.show_list()

    def get_plugins_privkey(self) -> Optional['ECPrivkey']:
        pubkey, salt = self.plugins.get_pubkey_bytes()
        if not pubkey:
            self.init_plugins_password()
            return
        # ask for url and password, same window
        pw = self.password_dialog(
            msg=' '.join([
                _('<b>Warning</b>: Third-party plugins are not endorsed by Electrum!'),
                '<br/><br/>',
                _('If you install a third-party plugin, you trust the software not to be malicious.'),
                _('Electrum will not be responsible in case of theft, loss of funds or privacy that might result from third-party plugins.'),
                _('You should at minimum check who the author of the plugin is, and be careful of imposters.'),
                '<br/><br/>',
                _('Please enter your plugin authorization password') + ':'
            ])
        )
        if not pw:
            return
        privkey = self.plugins.derive_privkey(pw, salt)
        if pubkey != privkey.get_public_key_bytes():
            keyfile_path, keyfile_help = self.plugins.get_keyfile_path()
            self.show_error(
                ''.join([
                    _('Incorrect password.'), '\n\n',
                    _('Your plugin authorization password is required to install plugins.'), ' ',
                    _('If you need to reset it, remove the following file:'), '\n\n',
                    keyfile_path
                ]))
            return
        return privkey

    def init_plugins_password(self):
        from .password_dialog import NewPasswordDialog
        msg = ' '.join([
            _('In order to install third-party plugins, you need to choose a plugin authorization password.'),
            _('Its purpose is to prevent unauthorized users (or malware) from installing plugins.'),
        ])
        d = NewPasswordDialog(self, msg=msg)
        pw = d.run()
        if not pw:
            return
        key_hex = self.plugins.create_new_key(pw)
        keyfile_path, keyfile_help = self.plugins.get_keyfile_path()
        msg = '\n\n'.join([
            _('Your plugins key is:'), key_hex,
            _('This key has been copied to your clipboard. Please save it in:'),
            keyfile_path,
            keyfile_help,
            '',
        ])
        clipboard = QApplication.clipboard()
        clipboard.setText(key_hex)
        self.show_message(msg)

    def download_plugin_dialog(self):
        import os
        from .util import line_dialog
        from electrum.util import UserCancelled
        pubkey, salt = self.plugins.get_pubkey_bytes()
        if not pubkey:
            self.init_plugins_password()
            return
        url = line_dialog(self, 'url', _('Enter plugin URL'), _('Download'))
        if not url:
            return
        coro = self.plugins.download_external_plugin(url)
        try:
            path = self.window.run_coroutine_dialog(coro, _("Downloading plugin..."))
        except UserCancelled:
            return
        except Exception as e:
            self.show_error(f"{e}")
            return
        try:
            success = self.add_external_plugin(path)
        except Exception as e:
            self.show_error(f"{e}")
            success = False
        if not success:
            os.unlink(path)

    def add_plugin_dialog(self):
        pubkey, salt = self.plugins.get_pubkey_bytes()
        if not pubkey:
            self.init_plugins_password()
            return
        filename, __ = QFileDialog.getOpenFileName(self, _("Select your plugin zipfile"), "", "*.zip")
        if not filename:
            return
        plugins_dir = self.plugins.get_external_plugin_dir()
        path = os.path.join(plugins_dir, os.path.basename(filename))
        shutil.copyfile(filename, path)
        try:
            success = self.add_external_plugin(path)
        except Exception as e:
            self.show_error(f"{e}")
            success = False
        if not success:
            os.unlink(path)

    def add_external_plugin(self, path):
        manifest = self.plugins.read_manifest(path)
        name = manifest['name']
        d = PluginDialog(name, manifest, None, self)
        if not d.exec():
            return False
        # ask password once user has approved
        privkey = self.get_plugins_privkey()
        if not privkey:
            return False
        self.plugins.install_external_plugin(name, path, privkey, manifest)
        self.show_list()
        return True

    def add_internal_plugin(self, name):
        """ simply set the config """
        manifest = self.plugins.internal_plugin_metadata[name]
        d = PluginDialog(name, manifest, None, self)
        if not d.exec():
            return False
        self.plugins.install_internal_plugin(name)
        self.show_list()

    def show_list(self):
        descriptions = self.plugins.descriptions
        descriptions = sorted(descriptions.items())
        grid = self.grid
        # clear existing items
        for i in reversed(range(grid.count())):
            grid.itemAt(i).widget().setParent(None)
        # populate
        i = 0
        for name, metadata in descriptions:
            i += 1
            if self.plugins.is_internal(name) and self.plugins.is_auto_loaded(name):
                continue
            if not self.plugins.is_installed(name):
                continue
            display_name = metadata.get('fullname')
            if not display_name:
                continue
            label = IconLabel(text=display_name, reverse=True)
            icon_path = metadata.get('icon')
            if icon_path:
                icon = read_QIcon_from_bytes(self.plugins.read_file(name, icon_path))
                label.setIcon(icon)
            label.status_button = PluginStatusButton(self, name)
            grid.addWidget(label, i, 0)
            grid.addWidget(label.status_button, i, 1)
        # add stretch
        grid.setRowStretch(i + 1, 1)

    def do_toggle(self, name, status_button):
        if not self.plugins.is_authorized(name):
            #self.show_plugin_dialog(name, status_button)
            return
        if self.plugins.is_auto_loaded(name):
            return
        p = self.plugins.get(name)
        is_enabled = p and p.is_enabled()
        if is_enabled:
            self.plugins.disable(name)
        else:
            self.plugins.enable(name)
        if status_button:
            status_button.update()
        if self.gui_object:
            self.gui_object.reload_windows()
        self.setFocus()
        self.activateWindow()

    def uninstall_plugin(self, name):
        if not self.question(_('Remove plugin \'{}\'?').format(name)):
            return
        self.plugins.uninstall(name)
        if self.gui_object:
            self.gui_object.reload_windows()
        self.show_list()
