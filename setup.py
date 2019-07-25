import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="telemeter_sla_reporter-reporter",
    version="0.0.1",
    author="Anthony Byrne",
    author_email="abyrne@redhat.com",
    description="A tool for generating SLA compliance reports based on Telemeter data.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/abyrne55/telemeter-sla-reporter",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3.7",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Natural Language :: English"
    ],
)