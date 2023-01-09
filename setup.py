from setuptools import setup, find_packages
import pathlib

here = pathlib.Path(__file__).parent.resolve()

# Get the long description from the README file
LONG_DESCRIPTION = (here / "README.md").read_text(encoding="utf-8")

VERSION = "1.3.0"

# Setting up
setup(
    name="carrier_api",
    version=VERSION,
    author="Brendan Dahl",
    author_email="dahl.brendan@gmail.com",
    description="Carrier Api Wrapper",
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=["xmltodict", "requests-oauthlib", "requests"],
    keywords=["carrier", "api"],
    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Operating System :: MacOS :: MacOS X",
    ],
    python_requires=">=3.10, <4",
    url="https://github.com/dahlb/carrier_api",
    project_urls={
        "Bug Reports": "https://github.com/dahlb/carrier_api/issues",
        "Source": "https://github.com/dahlb/carrier_api",
    },
)
