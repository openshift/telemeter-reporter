import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(name="telemeter-reporter", version="0.1.1", author="Anthony Byrne",
                 author_email="abyrne@redhat.com",
                 description="A tool for generating compliance reports based on Telemeter data.",
                 long_description=long_description, long_description_content_type="text/markdown",
                 url="https://github.com/abyrne55/telemeter-reporter",
                 scripts=['bin/telemeter-reporter'], packages=setuptools.find_packages(),
                 install_requires=['PyYAML>=5.1.1', 'certifi>=2019.6.16', 'requests>=2.22.0',
                                   'PyJWT>=1.7.1', 'prometheus_api_client>=0.0.1',
                                   'tabulate>=0.8.3', 'typing>=3.7.4'],
                 classifiers=["Programming Language :: Python :: 3.7",
                              "License :: OSI Approved :: Apache Software License",
                              "Operating System :: OS Independent",
                              "Natural Language :: English"], )
