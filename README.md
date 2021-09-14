# Trading portfolio

This is a webapp that allows you to track your portfolio's performance from day 1. It aggregates multiple brokerage accounts in the same place. It's possible to visualise the historical gains and value, the composition, the exposure and the holdings. 

{{<img src="https://user-images.githubusercontent.com/47567574/119206243-de2aaa00-ba9a-11eb-8764-a39df00e5d92.gif"  caption="Trading portfolio screenshots" align="center">}}

## Installation
First clone the project as follows:
```bash
git clone git@github.com:bdebbabi/trading-portfolio.git
```  
You also have to install the required packages. You will have to run the following command:
```bash
pip install -r requirements.txt
```

Then you will need to add your authentification settings by modifying the ```settings.yaml``` file.
For now transactions are automatically retrieved for Degiro and Coinbase using their API. For the other accounts transactions should be added manually in ```data/other_transactions.csv```.

Add you username and password. If you have a 2-step authentification enabled in your Degiro account you have to add your authentification key, otherwise leave it empty. 
For more protection you can also write your authentification settings encoded into base64. You can use this [website](https://www.base64encode.org/) in order to do that. You will have to change ```HASHED``` to ```True``` in that case.
You also have to add the account creation date.
```YAML
AUTHENTIFICATION:
  DEGIRO:
    USERNAME: 
    PASSWORD: 
    KEY: 
  COINBASE:
    API_KEY: 
    API_SECRET: 
  HASHED: True #True if the above parameters are enconded in base64
CREATION_DATE: '2020-01-09' #Account creation date in the following format 'YYYY-MM-DD'
DEBUG: True #Change to True to allow live debbuging 
```

## Usage
This app is run on localhost. Use the following command to launch it:
```bash
cd src
python app.py
```

