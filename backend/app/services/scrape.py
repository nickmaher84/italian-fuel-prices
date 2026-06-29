from app.scraper.historic import HistoricScraper


def historic_scrape():
    historic = HistoricScraper()
    historic.run()
