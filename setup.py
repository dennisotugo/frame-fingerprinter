from setuptools import setup, find_packages

setup(
    name="frame-fingerprinter",
    version="0.1.0",
    description=(
        "Frame-by-frame cryptographic verifier for video – "
        "designed for dashcams and recording devices."
    ),
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Frame Fingerprinter Contributors",
    license="MIT",
    python_requires=">=3.10",
    packages=find_packages(exclude=["tests*"]),
    install_requires=[
        "numpy>=1.24.0",
        "python-gnupg>=0.5.0",
    ],
    extras_require={
        "dev": ["pytest>=7.0.0", "Pillow>=10.0.0"],
    },
    entry_points={
        "console_scripts": [
            "fingerprint-video=fingerprint_video:main",
            "verify-video=verify_video:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Legal Industry",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Multimedia :: Video",
        "Topic :: Security :: Cryptography",
    ],
)
