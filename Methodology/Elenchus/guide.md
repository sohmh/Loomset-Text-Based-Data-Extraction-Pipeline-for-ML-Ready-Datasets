This is a guide on how to setup, use and edit the LoomSet Tutor Socratic Model.
I am using qwen3:8b model with the ollama architecture. 

1. How to run the qwen3:8b model?
    - In windows powershell run :  `ollama run qwen3:8b`
    - Then the model will run and you can ask questions, it will provide answers
    - To exit the model run : `/bye`
2. How to use the model in this project?
    - First make sure you're in the right directory by clicking on LoomSet Tutor folder and -> Open in Integrated Terminal
    - Then type `dir` -> you should see "ModelFile" -> This file is the set of instructions we are using as context for our tutor model
    - Now create the custom tutor model by using ollama with the model file, run in the integrated terminal : `ollama create elenchus -f Modelfile`
    - Now check to see if it exists by listing all the models in your ollama architecture : `ollama list`
    - Now you can run the tutor model to ask questions : `ollama run elenchus --think=false`
    - use `/bye` to exit the model.
    - to stop the model from answering you can use `Ctrl+C`
3. How to edit the model?
    - Everytime you want to editthe model instructions , simply go to `ModelFile`, make your changes and save with `Ctrl+S`
    - Then in the terminal inside LoomSet Tutor, Run : `ollama create elenchus -f Modelfile` and wait for success, that's it.

4. How to run the bot (the encapsulated project)?
    - In Elenchus, start the python virtual environment by running `.\.venv\Scripts\Activate.ps1`
    - then run `python bot.py`
    