# Installation

1. Start by cloning the repository to your local machine:

        git clone https://github.com/mxcube/argussight
        cd argussight

1. Optionally, you can create and activate a [conda](https://docs.conda.io/projects/conda/en/latest/index.html) environment like this:

        conda env create -f conda-environment.yml
        conda activate argussight

    > **Note**: If you skip this part, please make sure to have all necessary packages from `conda-environment.yml` installed.

1. Install all dependencies necessary for the code to run, using `poetry`, run:

        poetry install

1. If you followed the above steps and everything ran without any issues, you can proceed to the [Setup page](usage/setup.md) to start using the project. However, if you encounter any problems, be sure to check out our [FAQ](faq.md) section for common issues and solutions. If your issue isn't listed, feel free to write an [issue](https://github.com/mxcube/argussight/issues) on our GitHub repository.
