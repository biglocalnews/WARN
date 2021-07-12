import datetime
import logging
from os.path import exists
import re
import requests
import urllib3

from bs4 import BeautifulSoup
import pdfplumber
import tenacity

from warn.cache import Cache
from warn.utils import write_rows_to_csv

logger = logging.getLogger(__name__)

# scrape all links from WARN page http://floridajobs.org/office-directory/division-of-workforce-services/workforce-programs/reemployment-and-emergency-assistance-coordination-team-react/warn-notices
def scrape(output_dir, cache_dir=None):
    output_csv = '{}/fl.csv'.format(output_dir)
    cache = Cache(cache_dir)  # ~/.warn-scraper/cache
    # FL site requires realistic User-Agent.
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.102 Safari/537.36'
    }
    url = 'http://floridajobs.org/office-directory/division-of-workforce-services/workforce-programs/reemployment-and-emergency-assistance-coordination-team-react/warn-notices'
    response = requests.get(url, headers=headers, verify=False)
    logger.debug(f"Request status is {response.status_code} for {url}")
    soup = BeautifulSoup(response.text, 'html.parser')
    # find & visit each year's WARN page
    links = soup.find_all('a', href=re.compile('^http://reactwarn.floridajobs.org/WarnList/'))
    output_rows = []
    header_written = False
    # scraped most recent year first
    for year_url in links:
        year_url = year_url.get('href')  # get URL from link
        if 'PDF' in year_url:
            rows_to_add = scrape_pdf(cache, cache_dir, year_url, headers)
        else:
            html_pages = scrape_html(cache, year_url, headers)
            rows_to_add = html_to_rows(html_pages, output_csv)
            # write the header only once
            if not header_written:
                output_rows.append(write_header(html_pages))
                header_written = True
        [output_rows.append(row) for row in rows_to_add]  # moving from one list to the other
    write_rows_to_csv(output_rows, output_csv)
    return output_csv

# scrapes each html page for the current year
# returns a list of the year's html pages
# note: no max amount of retries (recursive scraping)
@tenacity.retry(wait=tenacity.wait_exponential(),
                retry=tenacity.retry_if_exception_type(requests.HTTPError))
def scrape_html(cache, url, headers, page=1):
    urllib3.disable_warnings()  # sidestep SSL error
    # extract year from URL
    year = re.search(r'year=([0-9]{4})', url, re.I).group(1)
    html_cache_key = f'fl/{year}_page_{page}'
    current_year = datetime.date.today().year
    last_year = str(current_year - 1)
    current_year = str(current_year)
    page_text = ""
    # search in cache first before scraping
    try:
        # always re-scrape current year and prior year just to be safe
        # note that this strategy, while safer, spends a long time scraping 2020.
        if True:  # not (year == current_year) and not (year == last_year) # TODO DO NOT CACHE NEWEST for debugging only
            logger.debug(f'Trying to read from cache: {html_cache_key}')
            cachefile = cache.read(html_cache_key)
            page_text = cachefile
            logger.debug(f'Page fetched from cache: {html_cache_key}')
        else:
            raise FileNotFoundError
    except FileNotFoundError:
        # scrape & cache html
        response = requests.get(url, headers=headers, verify=False)
        logger.debug(f"Request status is {response.status_code} for {url}")
        response.raise_for_status()
        page_text = response.text
        cache.write(html_cache_key, page_text)
        logger.debug(f"Successfully scraped page {url} to cache: {html_cache_key}")

    logger.debug(f"<br> has occurred? {'<br>' in page_text}")
    page_text = page_text.replace("<br>", "\n")
    # search the page we just scraped for links to the next page
    soup = BeautifulSoup(page_text, 'html.parser')
    footer = soup.find('tfoot')
    if footer:
        next_page = page + 1
        nextPageLink = footer.find('a', href=re.compile(f'page={next_page}'))  # find link to next page, if exists
        # recursively scrape until we have a list of all the pages' html
        if nextPageLink:
            url = 'http://reactwarn.floridajobs.org' + nextPageLink.get('href')  # /WarnList/Records?year=XXXX&page=X
            # recursively make list of all the next pages' html
            pages_html = scrape_html(cache, url, headers, next_page)
            # add the current page to the recursive list
            pages_html.append(page_text)
            return pages_html
    # last page reached
    return [page_text]


# takes list of html pages, outputs list of data rows
def html_to_rows(page_text, output_csv):
    output_rows = []
    for page in page_text:
        soup = BeautifulSoup(page, 'html5lib')
        table = soup.find('table')
        # extract table data
        tbody = table.find('tbody')
        for table_row in tbody.find_all('tr'):
            columns = table_row.find_all('td')
            output_row = []
            for column in columns:
                output_row.append(column.text.strip())
            output_rows.append(output_row)
    return output_rows


# extract table headers from thead--only do so once
def write_header(pages):
    page = pages[0]
    soup = BeautifulSoup(page, 'html5lib')
    table = soup.find('table')
    thead = table.find('thead')
    headers = thead.find_all('th')
    output_rows = []
    for header in headers:
        output_rows.append(header.text.strip())
    return output_rows


@tenacity.retry(wait=tenacity.wait_exponential(),
                retry=tenacity.retry_if_exception_type(requests.HTTPError))
def scrape_pdf(cache, cache_dir, url, headers):
    # sidestep SSL error
    urllib3.disable_warnings()
    # extract year from URL
    year = re.search(r'year=([0-9]{4})', url, re.I).group(1)
    pdf_cache_key = f'fl/{year}'
    download = ""
    # download pdf if not in the cache
    if not exists(pdf_cache_key):
        response = requests.get(url, headers=headers, verify=False)
        logger.debug(f"Request status is {response.status_code} for {url}")
        response.raise_for_status()
        # download & cache pdf
        download = response.content
        with open(f"{cache_dir}/{pdf_cache_key}.pdf", 'wb') as f:
            f.write(download)
        logger.debug(f"Successfully scraped PDF from {url} to cache: {pdf_cache_key}")
    # scrape tables from PDF
    with pdfplumber.open(f"{cache_dir}/{pdf_cache_key}.pdf") as pdf:
        pages = pdf.pages
        output_rows = []
        for page_num, page in enumerate(pages):
            table = page.extract_table(table_settings={})
            # remove each year's header
            if page_num == 0:
                table.pop(0)
            table = clean_table(table, output_rows)
            output_rows.extend(table)  # merging lists
    logger.debug(f"Successfully scraped PDF from {url}")
    return output_rows


# adds split rows to output_rows by reference, returns list of page's rows to be added
def clean_table(table, all_rows=[]):
    table_rows = []
    for row_idx, row in enumerate(table):
        current_row = []
        # fix row splitting b/n pages
        if is_multiline_row(row_idx, row):
            if len(row) > 5:  # fix where both row is split AND columns skewed right (like page 14 of 2016.pdf)
                row = [row[0], row[1], row[2], row[3], row[6]]
            for field_idx, field_to_add in enumerate(row):
                if field_to_add:
                    all_rows[-1][field_idx] += field_to_add  # MERGE fields with last row from all_rows (i.e. the last row from prior page)
            continue
        for field_idx, field in enumerate(row):
            # ignore any redundant header rows
            if is_header_row(field_idx, field):
                break
            # fix column skew by skipping blank columns
            if field:
                clean_field = field.strip()
                if clean_field:
                    current_row.append(clean_field)
        if current_row:
            table_rows.append(current_row)
    return table_rows


def is_multiline_row(row_idx, row):
    # this is a row that has been split between pages
    # we want to remedy this split in the output data
    return (row_idx == 0 and row[1] == "" and row[3] == "")

def is_header_row(field_idx, field):
    # we already have a header management strategy
    # but there are still erroneous redundant headers strewn about
    # and we need to remove them from the data
    # because we only need 1 header row.
    return (field_idx == 0 and field == "COMPANY NAME")
