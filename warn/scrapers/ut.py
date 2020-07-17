import csv
import requests

from bs4 import BeautifulSoup

# spot-check once more

def scraper():

    output_csv = '/Users/dilcia_mercedes/Big_Local_News/prog/WARN/data/utah_warn_raw.csv'

    url = 'https://jobs.utah.gov/employer/business/warnnotices.html'
    page = requests.get(url)

    print(page.status_code) # should be 200

    soup = BeautifulSoup(page.text, 'html.parser')

    tables = soup.find_all('table') # output is list-type
    len(tables)

    # find header
    first_row = tables[0].find_all('tr')[0]
    headers = first_row.find_all('th')
    output_header = []
    for header in headers:
        output_header.append(header.text)
    output_header = [x.strip() for x in output_header]
    output_header

    # save header
    with open(output_csv, 'w') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(output_header)

    for table in tables:
        output_rows = []
        for table_row in table.find_all('tr'):    
            columns = table_row.find_all('td')
            output_row = []
            for column in columns:
                output_row.append(column.text)
            output_row = [x.strip() for x in output_row]
            output_rows.append(output_row)
        output_rows.pop(0)
        # print(output_rows[0])
        
        if len(output_rows) > 0:
            with open(output_csv, 'a') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerows(output_rows)


if __name__ == '__main__':
    scraper()