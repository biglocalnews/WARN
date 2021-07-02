import csv
import logging
import re
import requests

from bs4 import BeautifulSoup

from warn.utils import write_rows_to_csv


logger  = logging.getLogger(__name__)


def scrape(output_dir, cache_dir=None):
    output_csv = f'{output_dir}/al.csv'
    url = 'https://www.madeinalabama.com/warn-list/'
    logger.debug(f'Scraping {url}')
    page = requests.get(url)
    # can't see 2020 listings when I open web page, but they are on the summary in the google search
    soup = BeautifulSoup(page.text, 'html.parser')
    table = soup.find_all('table') # output is list-type
    table_rows = table[0].find_all('tr')
    # Handle the header
    raw_header = table_rows.pop(0)
    header_row = extract_fields_from_row(raw_header, 'th')
    output_rows = [header_row]
    # Process remaining rows
    discarded_rows = []
    for table_row in table_rows:
        # Discard bogus data lines (see last lines of source data)
        # based on check of first field ("Closing or Layoff")
        data = extract_fields_from_row(table_row, 'td')
        layoff_type = data[0]
        if re.match(r'(clos|lay)', layoff_type, re.I):
            output_rows.append(data)
        else:
            discarded_rows.append(data)
    if discarded_rows:
        logger.warn(f"Warning: Discarded {len(discarded_rows)} dirty data row(s)")
    write_rows_to_csv(output_rows, output_csv)
    return output_csv


def extract_fields_from_row(row, element):
    row_data = []
    fields = row.find_all(element)
    for raw_field in fields:
        field = raw_field.text.strip()
        row_data.append(field)
    return row_data
