from setuptools import setup

setup(
    name = 'openssh-mux-mon',
    version = '1.0',
    author = 'Bert Wesarg',
    author_email = 'bertwesarg@users.noreply.github.com',
    description = 'A AppIndicator to monitor OpenSSH connections',
    license = '3-clause BSD',
    url = 'https://github.com/bertwesarg/openssh-mux-mon',
    scripts = ['muxmon.py', 'pysshmux.py'],
    install_requires = [
        'pygtk>=2.24',
        'appindicator>=12.10.1',
        'pynotify>=0.1.1',
        'pyinotify>=0.9.5',
    ]
)
