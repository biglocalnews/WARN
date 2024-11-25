import logging
import re
from glob import glob
from importlib import reload
from pathlib import Path
import datetime

import pdfplumber
from bs4 import BeautifulSoup

from .. import utils
from ..cache import Cache

__authors__ = ["Ash1R", "stucka"]
__tags__ = ["html", "pdf"]
__source__ = {
    "name": "Mississippi Department of Employment Security",
    "url": "https://mdes.ms.gov/information-center/warn-information/",
}

reload(logging)
logging.basicConfig(
    format="%(asctime)s %(levelname)s:%(message)s",
    level=logging.DEBUG,
    datefmt="%I:%M:%S",
)
logger = logging.getLogger(__name__)


def is_not_bad_rect(obj):
    """Filter out bad objects from PDFs."""
    if obj["object_type"] == "rect":
        return obj["width"] < 2 or obj["height"] < 2
    else:
        return True


def clean_text(blob):
    """Replace newlines and other junk pulled from PDFs."""
    blob = (
        blob.replace("\r", " ")
        .replace("\n", " ")
        .replace("   ", " ")
        .replace("  ", " ")
        .replace("–", "--")  # Weird dashes coming through NAICS fields
        .replace("–", "--")
        .replace("’", "'")
        .replace("Company Name (City) (County) (Zip)", "")
        .strip()
    )
    return blob


def nuke_bad_fields(incoming: list, extraignores: list = []):
    """Given a list of lists, identify empty fields/columns and delete them.

    Arguments:
        List of lists,
        Optional: List of items to ignore besides "" and None
    Returns:
        List of lists
        List of fields purged
        List of data items purged
    """
    if not incoming:
        return (None, None, None)
    totalignores = ["", None]
    totalignores.extend(extraignores)
    # Need to check if table is null, doesn't contain lists of lists, whatever
    badfields = []
    for field in incoming[0]:
        badfields.append(True)
    for rowindex, row in enumerate(incoming):
        if len(row) != len(badfields):
            print(
                f"Irregular counts of fields. Table not standardized. Aborting from row {rowindex}."
            )
            break
        else:
            for fieldindex, item in enumerate(row):
                if item not in totalignores:
                    badfields[fieldindex] = False
    badfieldtally = []
    for badfieldindex, badfield in enumerate(badfields):
        if badfield:
            badfieldtally.append(badfieldindex)
    badfieldtally = list(reversed(badfieldtally))
    trasheditems = []
    if len(badfieldtally) > 0:
        # print(f"Attempting to delete {len(badfieldtally):,} fields at {badfieldtally}")
        for rowindex in range(0, len(incoming)):
            for badfield in badfieldtally:
                trasheditems.append(incoming[rowindex].pop(badfield))
    return (incoming, badfieldtally, trasheditems)


def scrape(
    data_dir: Path = utils.WARN_DATA_DIR,
    cache_dir: Path = utils.WARN_CACHE_DIR,
) -> Path:
    """
    Scrape data from Mississippi.

    Keyword arguments:
    data_dir -- the Path were the result will be saved (default WARN_DATA_DIR)
    cache_dir -- the Path where results can be cached (default WARN_CACHE_DIR)

    Returns: the Path where the file is written
    """
    archived_pdfs = [
        "/media/406616/py2022_q4_warn_apr2023_jun2023.pdf",
        "/media/397321/py2022_q3_warn_jan2023_mar2023.pdf",
        "/media/391018/py2022_q2_warn_oct2022_dec2022.pdf",
        "/media/382687/py2022_q1_warn_july2022_sept2022.pdf",
        "/media/372199/py2021_q4_warn_apr2022_jun2022.pdf",
        "/media/355823/py2021_q3_warn_jan2022_mar2022.pdf",
        "/media/341054/py2021_q2_warn_oct2021_dec2021.pdf",
        "/media/327617/py2021_q1_warn_july2021_sept2021.pdf",
        "/media/312879/py2020_q4_warn_apr2021_jun2021.pdf",
        "/media/282830/py2020_q3_warn_jan2021_mar2021.pdf",
        "/media/282824/py2020_q2_warn_oct2020_dec2020.pdf",
        "/media/230832/py2020_q1_warn_july2020_sept2020.pdf",
        "/media/204780/py2019_q4_warn_apr2020_jun2020.pdf",
        "/media/180956/py2019_q3_warn_jan2020_mar2020.pdf",
        "/media/165147/py2019_q2_warn_oct2019_dec2019.pdf",
        "/media/160518/py2019_q1_warn_july2019_sept2019.pdf",
        "/media/152801/py2018_q4_warn_apr2019_jun2019.pdf",
        "/media/144111/py2018_q3_warn_jan2019_mar2019.pdf",
        "/media/141119/py2018_q2_warn_oct2018_dec2018.pdf",
        "/media/128907/py2018_q1_warn_july2018_sept2018.pdf",
        "/media/123921/py2017_q4_warn_apr2018_jun2018.pdf",
        "/media/118119/py2017_q3_warn_jan2018_mar2018.pdf",
        "/media/109393/py2017_q2_warn_oct2017_dec2017.pdf",
        "/media/100974/py2017_q1_warn_july2017_sept2017.pdf",
        "/media/96181/py2016_q4_warn_apr2017_jun2017.pdf",
        "/media/91268/py2016_q3_warn_jan2017_mar2017.pdf",
        "/media/85903/py2016_q2_warn_oct2016_dec2016.pdf",
        "/media/77287/py2016_q1_warn_july2016_sept2016.pdf",
        "/media/73387/py2015_q4_warn_apr2016_jun2016.pdf",
        "/media/73382/py2015_q3_warn__jan2016_mar2016.pdf",
        "/media/61193/py2015_q2_warn___oct2015_dec2015.pdf",
        "/media/50387/py2015_q1_warn_jul2015_sep2015.pdf",
        "/media/42390/py2014_q4__warn_apr2015_jun2015.pdf",
        "/media/67606/py2014_q3_warn__jan2015_mar2015.pdf",
        "/media/37211/PY2014_Q2_WARN__Oct2014_Dec2014.pdf",
        "/media/36303/PY2014_Q1_WARN_Jul2014_Sep2014.pdf",
        "/media/35197/PY2013_Q4__WARN_Apr2014_Jun2014.pdf",
        "/media/33167/PY2013_Q3__WARN_Jan2014_Mar2014.pdf",
        "/media/31723/PY2013_Q2__WARN_Oct2013_Dec2013.pdf",
        "/media/30968/PY2013_Q1_WARN_Jul2013_Sep2013.pdf",
        "/media/26905/PY2012_Q1_WARN_Jul2012_Sep2012.pdf",
        "/media/26908/PY2012_Q2_WARN_Oct2012_Dec2012.pdf",
        "/media/26911/PY2012_Q3_WARN__Jan2013_Mar2013.pdf",
        "/media/29948/PY2012_Q4_WARN_Apr2013_Jun2013.pdf",
        "/media/26893/PY2011_Q1_WARN_July2011_Sep2011.pdf",
        "/media/26896/PY2011_Q2_WARN_Oct2011_Dec2011.pdf",
        "/media/26899/PY2011_Q3_WARN_Jan2012_Mar2012.pdf",
        "/media/26958/PY2011_Q4_WARN_Apr2012_Jun2012.pdf",
        "/media/26881/PY2010_Q1_WARN_Jul2010_Sep2010.pdf",
        "/media/26884/PY2010_Q2_WARN_Oct2010_Dec2010.pdf",
        "/media/123959/py2010_q3_warn_jan2011_mar2011.pdf",
        "/media/26890/PY2010_Q4_WARN_Apr2011_Jun2011.pdf",
    ]

    cache = Cache(cache_dir)

    # Grab the page
    page = utils.get_url("https://mdes.ms.gov/information-center/warn-information/")
    html = page.text
    soup = BeautifulSoup(html, "html5lib")
    all_pdf_links = soup.select("a[href*=pdf]")

    # Ash1R had drafted a beautiful list comprehension in here and stucka is wrecking it.
    links = []
    for link in all_pdf_links:
        href = link["href"]
        if "map" not in href.lower():
            # HEY!!!!!!!!!!!!!!!!!!!!!!!! if href not in archived_pdfs:
            links.append(f"https://mdes.ms.gov{href}")
    links = [
        f"https://mdes.ms.gov{link['href']}"
        for link in all_pdf_links
        if "map" not in link["href"]
    ]
    pdf_list = []

    # We want to make sure we have all the needed PDF files -- a copy of all the old ones.
    # But also want to grab the two latest PDFs to make sure we didn't miss anything new.
    for linkindex, link in enumerate(links):
        cache_key = "ms/" + link.split("/")[-2] + "_" + link.split("/")[-1]
        if cache.exists(cache_key) and linkindex >= 2:
            pdf_file = cache_dir / cache_key
        else:
            pdf_file = cache.download(cache_key, link)
        pdf_list.append(pdf_file)

    # HEY! Should pull from glob here.
    localfiles = glob(str(cache_dir) + "/ms/*.pdf")    

    logger.debug(f"Planning to process {len(pdf_list):,} PDFs.")

    extraheadersperrow = 6  # affected, countyish, file, page, sort_date, original_order
    dict_headers = [
        "Date",
        "Company City (County) Zip",
        "Workforce Area",
        "Event Number",
        "NAICS Code - Description",
        "Type",
        "Date of Action",
        "Comments",
        "Affected",
        "Countyish",
        "File",
        "Page",
        "sort_date",
        "original_order",
    ]
    rowwidth = len(dict_headers) - extraheadersperrow
    affectedindex = 5  # Column where the jobs/affected are found
    locationindex = 1  # Column with location
    locationfinder = re.compile(r"\((.*?)\)", flags=re.MULTILINE)
    table_settings = {
        "snap_x_tolerance": 3,
    }

    badpairs = 0
    final_data = []

    for file in localfiles:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                # Filter out pages with extra useless rectangles here
                text = page.filter(is_not_bad_rect).extract_tables(
                    table_settings=table_settings
                )

                # Filter out pages with empty column/field. Only one file from 2020 really fits here.
                for tableindex, localtable in enumerate(text):
                    if localtable:
                        localtable, fieldspurged, dataitemspurged = nuke_bad_fields(
                            localtable
                        )
                        if fieldspurged != []:
                            logger.debug(f"From file {file}, purged fields {fieldspurged} of contents {dataitemspurged}")
                        text[tableindex] = localtable
                if not text:
                    continue
                for i in range(len(text)):
                    if (
                        text[i][0][0]
                        and len(text[i][0][0]) > 1
                        and ("date" in text[i][0][0].lower())
                    ):
                        notices = text[i]
                        break

                # Check for signs this is the summary at the end of the PDF, which can be skipped.
                startrow = 0
                end_table = False
                while notices[startrow][0] is None or "/" not in notices[startrow][0]:
                    startrow += 1
                    if startrow == len(notices):
                        end_table = True
                        break
                if end_table:
                    continue
                # Start processing good data, which is broken into pairs of rows.
                for row in range(startrow, len(notices) - 1, 2):
                    line = {}
                    for item in dict_headers:
                        line[item] = None
                    # Check that row has the correct length.
                    if (
                        len(notices[row]) != rowwidth
                        or len(notices[row + 1]) != rowwidth
                    ):
                        badpairs += 1
                        logger.debug(
                            f"Row width miscount in {file}:\r\n  1 ({len(notices[row])}): {notices[row]}\r\n  2 ({len(notices[row+1])}): {notices[row+1]}"
                        )
                    elif notices[row][0] is None or "/" not in notices[row][0]:
                        continue
                    else:
                        for columnindex, item in enumerate(dict_headers[:rowwidth]):
                            cell = notices[row][columnindex]
                            if cell:  # If we get a None, we don't do anything else.
                                line[item] = clean_text(cell)
                        affected = notices[row + 1][affectedindex]
                        if affected:
                            line["Affected"] = clean_text(affected)
                        locationholder = notices[row][locationindex]
                        parentheses = locationfinder.findall(locationholder)
                        if parentheses:
                            line["Countyish"] = parentheses[-1]
                    line["File"] = file.replace("\\", "/").split("/")[-1]      # Give just the filename, not a path
                    line["Page"] = page
                    final_data.append(line)
    logger.debug(
        f"Done processing PDFs. Found {badpairs:,} bad pairs of data with wrong column counts."
    )
    logger.debug(f"{len(final_data):,} rows found.")

    for i, row in enumerate(final_data):
        localdate = row['Date']
        try:
            localdateobj = datetime.datetime.strptime(row['Date'], "%m/%d/%y")
        except Exception:
            try:
                localdateobj = datetime.datetime.strptime(row['Date'], "%m/%d/%Y")
            except Exception:
                localdateobj = datetime.datetime(2050, 12, 31)
        final_data[i]["sort_date"] = localdateobj.strftime("%Y-%m-%d")
        final_data[i]["original_order"] = i

    final_data = sorted(final_data, key=lambda x: x["sort_date"], reverse=True) 

    # Set the path to the final CSV
    output_csv = data_dir / "ms.csv"

    # Write out the rows to the export directory
    utils.write_dict_rows_to_csv(
        output_csv, dict_headers, final_data, mode="w", extrasaction="raise"
    )

    # Return the path to the final CSV
    return output_csv


if __name__ == "__main__":
    scrape()
