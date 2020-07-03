from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from pyotp import *
import base64
import re
import pandas as pd
from time import sleep 
import json
import requests

class webparser:

    def __init__(self, debug):
        self.debug = debug
        self.login()

    def login(self):
        with open('pass.bin', 'r') as file:
            username, password, key = [base64.b64decode(line).decode("utf-8") for line in file]


        options = Options()
        #options.add_argument('--start-maximized')
        if self.debug < 2:
            options.add_argument('--headless')
        
        self.driver = webdriver.Chrome(chrome_options=options)
        self.driver.set_window_size(1920, 1080)
        
        self.driver.get("https://trader.degiro.nl/trader/#/portfolio")
        wait = WebDriverWait(self.driver, 100)

        wait.until(EC.presence_of_element_located((By.ID, 'username')))
        self.driver.find_element_by_id('username').send_keys(username)
        self.driver.find_element_by_id ('password').send_keys(password)

        wait.until(EC.presence_of_element_located((By.NAME, 'loginButtonUniversal')))
        self.driver.find_element_by_name('loginButtonUniversal').click()

        wait.until(EC.presence_of_element_located((By.NAME, 'oneTimePassword')))
        totp = TOTP(key)
        token = totp.now()

        self.driver.find_element_by_css_selector("input[type='tel']").send_keys(token)
        self.driver.find_element_by_xpath("//button[@type='submit']").click()
        
        
    def go_to_portfolio(self):
        wait = WebDriverWait(self.driver, 100)
        
        wait.until(EC.presence_of_element_located((By.ID, 'appWorkspace')))
        self.driver.get("https://trader.degiro.nl/trader/#/portfolio")
        wait.until(EC.presence_of_element_located((By.ID, 'appWorkspace')))


    def get_session_ID(self):

        self.go_to_portfolio()
        
        wait = WebDriverWait(self.driver, 100)

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "button[data-name='exportButton']")))
        self.driver.find_element_by_xpath("//button[@data-name='exportButton']").click()
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-name='reportExportForm']")))

        link = self.driver.find_element_by_css_selector("div[data-name='reportExportForm']").find_elements_by_tag_name('a')[0]
        sessionID = re.search('sessionId=(.*)&country=', link.get_attribute("href")).group(1)

        return sessionID

    def get_positions(self):

        self.go_to_portfolio()
        
        wait = WebDriverWait(self.driver, 100)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-name='positions']")))
        sleep(2)

        position_tables = self.driver.find_elements_by_css_selector("div[data-name='positions']")
        positions = []
        for position_table in position_tables:
            tds = position_table.find_elements_by_tag_name('td')
            for td in tds:
                time = td.find_elements_by_tag_name('time')
                if time:
                    positions.append(time[0].get_attribute('datetime'))
                positions.append(td.text)
        
        positions = self.clean_positions(positions)
        return positions
    
    def clean_positions(self, positions, normalize=True):
        positions = [positions[i: i+12] for i in range(0, len(positions), 15)]
        positions = pd.DataFrame(positions, columns=['Produit', 'Place', 'Quantité','Price','Currency', 'Amount', 'PRU', '+/-', '+/-%', 'Gains without fees', 'Gains','Date'])
        positions['Produit'] = positions['Produit'].str[4:-2].str[:31].str.upper()
        positions.loc[positions['Produit'].str.len()==31, 'Produit'] = positions['Produit'].str.ljust(34,'.')
        positions['Gains without fees (%)'] = positions['Gains without fees'].str.partition('(')[2].str[:-2]
        positions['Gains without fees'] = positions['Gains without fees'].str.partition('(')[0]
        positions['+/-%'] = positions['+/-%'].str[:-1]
        positions['Quantité'] = positions['Quantité'].astype(int)
        positions['Price'] = positions['Price'].str[2:]
        positions['Date'] = pd.to_datetime(positions['Date']).dt.tz_convert("Europe/Paris").dt.tz_localize(None)

        if normalize:
            positions['Date'] = positions['Date'].dt.normalize()   
        for column in ['Price','Amount','PRU','+/-','+/-%','Gains without fees','Gains', 'Gains without fees (%)']:
            positions[column] = positions[column].str.replace(',','.').astype(float)

        positions['Gains (%)'] = (positions['Gains']/(positions['Amount'] - positions['Gains'])).round(2)
        
        sum = positions.sum()
        total_row = {'Produit':'Total', 'Amount': round(sum['Amount'], 2), 'Gains without fees': round(sum['Gains without fees'], 2), 'Gains': round(sum['Gains'],2), 'Date': positions.iloc[0]['Date'], 'Gains (%)': round((sum['Gains']/(sum['Amount'] - sum['Gains'])), 2), 'Gains without fees (%)': round((sum['Gains without fees']/(sum['Amount'] - sum['Gains without fees']) * 100), 2) }
        positions = positions.append(total_row, ignore_index=True)
        
        return positions

    def get_monetary_funds(self):

        accrued = self.driver.find_element_by_css_selector("span[data-id='accrued']")
        accrued = float(accrued.text.replace(',','.'))
        return accrued

    def get_account_summary(self):
        wait = WebDriverWait(self.driver, 100)

        # wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "button[data-name='totalPortfolioToggle']")))
        # self.driver.find_element_by_xpath("//button[@data-name='totalPortfolioToggle']").click()

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "section[data-name='accountSummary']")))
        sleep(2)

        summary = self.driver.find_elements_by_css_selector("section[data-name='accountSummary']")[0]

        spans = summary.find_elements_by_css_selector("span[data-id='totalPortfolio']")
        elements = [float(span.text[2:].replace(',','.')) for span in spans]

        

        # return portfolio_cash, portfolio, FM, cash, daily_gains, total_gains
        return elements
    
    def quit(self):
        # self.driver.quit()
        self.driver.close()

class mobile_parser():

    def __init__(self, debug):
        self.debug = debug
    
    def get_session_ID(self):
        with open('pass.bin', 'r') as file:
            username, password, key = [base64.b64decode(line).decode("utf-8") for line in file]
        totp = TOTP(key)
        token = totp.now()
        data = {"username":username,"password":password,"oneTimePassword":token}
        data = json.dumps(data)
        url = 'https://trader.degiro.nl/login/secure/login/totp'
        headers={'Content-Type': 'application/json'}
        
        session = requests.Session()
        r = session.post(url,headers=headers,data=data)

        return r.cookies['JSESSIONID']