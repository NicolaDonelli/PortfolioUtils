# python-template

This is a template project to be used as a standard, for any Python project.

## Repository initialization 

The template needs to be first initialised after creation using the script `bin/init_repo.sh`. 
The script will ask the user: 
    * the name to be used for the package 
    * the name to be used for the source folder
    * a short description of the project
    * the GCP project associated to the python project (if any)
The script will automatically consider the Python version in the current environment (Python versions greater than 
3.6 are supported) and take care of adapting configurations files according to input values and Python version.

**NOTE:** In the process, you will also be asked if you want to *remove the templates*, 
in order to keep your repo minimal and avoid cluttering. 
Please keep in mind that if you do so, you won't be able to re-initialise the files 
in your repository again.