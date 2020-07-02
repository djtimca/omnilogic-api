from distutils.core import setup
setup(
  name = 'omnilogic',
  packages = ['omnilogic'],
  version = '0.2.0',
  license='apache-2.0',
  description = 'Integration for the Hayward OmniLogic pool control system',
  author = 'Tim Empringham',
  author_email = 'tim.empringham@live.ca',
  url = 'https://github.com/djtimca/omnilogic',
  download_url = 'https://github.com/djtimca/omnilogic/archive/v_020.tar.gz',
  keywords = ['OmniLogic', 'Hayward', 'Pool', 'Spa'],
  install_requires=[
          'xmltodict',
          'config',
          'aiohttp',
      ],
  classifiers=[
    'Development Status :: 3 - Alpha',
    'Intended Audience :: Developers',
    'Topic :: Software Development :: Build Tools',
    'License :: OSI Approved :: Apache Software License',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.4',
    'Programming Language :: Python :: 3.5',
    'Programming Language :: Python :: 3.6',
  ],
)