from setuptools import setup

with open("README.md","r") as fh:
  long_description = fh.read()

setup(
  name = 'omnilogic',
  packages = ['omnilogic'],
  version = '0.4.6',
  license='apache-2.0',
  description = 'Integration for the Hayward OmniLogic pool control system',
  long_description = long_description,
  long_description_content_type = "text/markdown",
  author = 'Tim Empringham',
  author_email = 'tim.empringham@live.ca',
  url = 'https://github.com/djtimca/omnilogic-api',
  download_url = 'https://github.com/djtimca/omnilogic-api/archive/v_046.tar.gz',
  keywords = ['OmniLogic', 'Hayward', 'Pool', 'Spa'],
  install_requires=[
          'xmltodict',
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