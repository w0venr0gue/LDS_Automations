#script to transform data in a csv to an format that is consumable by ingestion software
import pandas
from tkinter import *
from tkinter.ttk import *
from tkinter.filedialog import askopenfile

#ask for file location
root = Tk()
root.geometry('200x100')

def open_file():
    filetypes = (('CSV files', '*.csv'),('All files', '*.*'))
    filename = filedialog.askopenfilename(title='Open a file', initialdir='/', filetypes=filetypes)

btn = Button(root, text="Choose JP Morgan CSV file", command = lambda:open_file())
btn.pack(side= TOP, pady = 10)


mainloop()
#filepath = 'C:\\Users\\cade\\Desktop\\Mom_project\\data.csv'
#filename = "data.csv"

#get contents of the original csv file but only specific columns
columns =['cherries', 'oranges']
csvFile = pandas.read_csv(filepath, usecols=columns)

print(csvFile)