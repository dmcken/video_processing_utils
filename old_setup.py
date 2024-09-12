from setuptools import setup, find_packages

with open('README.rst', encoding='UTF-8') as f:
  readme = f.read()

setup(
    name='video_processing',
    version='1.0.1',
    description='Command line user export utility',
    long_description=readme,
    author='Your Name',
    author_email='your_email@example.com',
    packages=find_packages('src'),
    package_dir={'': 'src'},
    install_requires=[],
    entry_points={
        'console_scripts': 'concat_video=concat_video.cli:main',
    },
)