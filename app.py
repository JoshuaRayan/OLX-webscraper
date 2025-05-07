import requests
from bs4 import BeautifulSoup
import json
import csv
import time
import random
import argparse
from datetime import datetime
import logging
from fake_useragent import UserAgent  

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('olx_scraper')

class StealthyScraper:
    def __init__(self):
        self.base_url = "https://www.olx.in/items/q-car-cover"
        self.ua = UserAgent()
        self.session = requests.Session()
        self.retry_delay = 30  # Seconds to wait after a blocked request
        
    def get_random_headers(self):
        """Generate random headers to look like different browsers"""
        return {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.google.com/',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
            'TE': 'Trailers',
        }

    def fetch_page(self, url, max_retries=3):
        """Fetch a page with retry logic and stealth measures"""
        retries = 0
        while retries < max_retries:
            try:
                # Wait a random time before request to seem more human-like
                wait_time = random.uniform(2, 5)
                logger.info(f"Waiting {wait_time:.2f}s before request...")
                time.sleep(wait_time)
                
                # Get fresh headers for each request
                headers = self.get_random_headers()
                logger.info(f"Fetching URL: {url}")
                
                # Make the request with a longer timeout
                response = self.session.get(url, headers=headers, timeout=20)
                
                # Check if we might be blocked
                if "captcha" in response.text.lower() or "detected unusual traffic" in response.text.lower():
                    logger.warning("CAPTCHA or anti-bot page detected! Retrying after delay...")
                    retries += 1
                    time.sleep(self.retry_delay)
                    continue
                    
                # If status code is not OK (200)
                if response.status_code != 200:
                    logger.warning(f"Got status code {response.status_code}. Retrying...")
                    retries += 1
                    time.sleep(self.retry_delay)
                    continue
                
                logger.info(f"Successfully fetched page (size: {len(response.text)} bytes)")
                return response.text
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error: {e}")
                retries += 1
                if retries < max_retries:
                    wait = self.retry_delay * retries  # Exponential backoff
                    logger.info(f"Retrying in {wait} seconds...")
                    time.sleep(wait)
                else:
                    logger.error("Max retries reached. Giving up on this URL.")
                    return None
        
        return None

    def parse_listing(self, listing):
        """Parse a single listing with flexible selectors"""
        try:
            # Try multiple possible class names for each field
            # Price selectors
            price_selectors = ['span._2Ks63', 'span.olx-price-new', 'span[data-aut-id="itemPrice"]', 
                              'span.price', 'span.text-price']
            # Title selectors
            title_selectors = ['span._2tW1I', 'span.olx-text-color', 'span[data-aut-id="itemTitle"]',
                              'h2', 'div.title']
            # Location selectors
            loc_selectors = ['span.tjgMj', 'span.olx-location', 'span[data-aut-id="item-location"]',
                            'span.location']
            # Date selectors
            date_selectors = ['span.zLvFQ', 'span.olx-date', 'span[data-aut-id="item-date"]',
                             'span.date']
            
            # Try each selector until one works
            price = "N/A"
            for selector in price_selectors:
                price_elem = listing.select_one(selector)
                if price_elem:
                    price = price_elem.text.strip()
                    break
                    
            title = "N/A"
            for selector in title_selectors:
                title_elem = listing.select_one(selector)
                if title_elem:
                    title = title_elem.text.strip()
                    break
                    
            location = "N/A"
            for selector in loc_selectors:
                loc_elem = listing.select_one(selector)
                if loc_elem:
                    location = loc_elem.text.strip()
                    break
                    
            date_posted = "N/A"
            for selector in date_selectors:
                date_elem = listing.select_one(selector)
                if date_elem:
                    date_posted = date_elem.text.strip()
                    break
            
            # Extract link - try multiple approaches
            link = "N/A"
            link_elem = listing.find('a')
            if link_elem and 'href' in link_elem.attrs:
                link = link_elem['href']
                if not link.startswith('http'):
                    link = "https://www.olx.in" + link
            
            # Extract image URL
            image_url = "N/A"
            img_elem = listing.find('img')
            if img_elem:
                for attr in ['src', 'data-src', 'srcset']:
                    if attr in img_elem.attrs:
                        image_url = img_elem[attr]
                        break
            
            return {
                'title': title,
                'price': price,
                'location': location,
                'date_posted': date_posted,
                'link': link,
                'image_url': image_url
            }
        except Exception as e:
            logger.error(f"Error parsing listing: {e}")
            return None

    def find_listings(self, html_content):
        """Find all listing elements with multiple possible selectors"""
        if not html_content:
            return []
            
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Try multiple possible selectors for listings
        listing_selectors = [
            'li.EIR5N', 
            'li[data-aut-id="itemBox"]', 
            'div[data-aut-id="itemCard"]',
            'div.IKo3_',  # Another possible class name
            'li.listing'
        ]
        
        for selector in listing_selectors:
            listings = soup.select(selector)
            if listings:
                logger.info(f"Found {len(listings)} listings using selector: {selector}")
                return listings
        
        # If we didn't find any listings using our selectors, try a more general approach
        logger.warning("No listings found with known selectors. Trying general approach.")
        
        # Look for divs or li elements that might contain listings
        potential_listings = soup.find_all(['div', 'li'], class_=True)
        
        # Filter potential listings that appear to have the right structure
        filtered_listings = []
        for item in potential_listings:
            # Check if it has both a title/heading and price - common for product listings
            has_heading = bool(item.find(['h2', 'h3', 'strong', 'span'], class_=True))
            has_price = bool(item.find(text=lambda t: '₹' in t if t else False))
            has_link = bool(item.find('a', href=True))
            
            if has_heading and (has_price or has_link):
                filtered_listings.append(item)
        
        if filtered_listings:
            logger.info(f"Found {len(filtered_listings)} potential listings using general approach")
            return filtered_listings
            
        logger.warning("No listings found on page")
        return []

    def scrape_search_results(self, max_pages=1):
        """Scrape search results using stealthy approach"""
        all_results = []
        current_page = 1
        
        while current_page <= max_pages:
            if current_page == 1:
                page_url = self.base_url
            else:
                page_url = f"{self.base_url}?page={current_page}"
                
            logger.info(f"Scraping page {current_page} of {max_pages}")
            
            html_content = self.fetch_page(page_url)
            if not html_content:
                logger.error(f"Failed to fetch page {current_page}. Moving to next page.")
                current_page += 1
                continue
            
            # Save HTML for debugging
            with open(f"olx_page_{current_page}.html", "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info(f"Saved HTML to olx_page_{current_page}.html for debugging")
            
            # Get all listings on the page
            listings = self.find_listings(html_content)
            
            # Process each listing
            page_results = []
            for listing in listings:
                result = self.parse_listing(listing)
                if result:
                    page_results.append(result)
            
            logger.info(f"Extracted {len(page_results)} listings from page {current_page}")
            all_results.extend(page_results)
            
            current_page += 1
            
            # Add longer random delay between pages
            if current_page <= max_pages:
                delay = random.uniform(10, 20)
                logger.info(f"Waiting {delay:.2f} seconds before next page...")
                time.sleep(delay)
        
        return all_results

    def save_to_json(self, data, filename):
        """Save data to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.info(f"Data saved to {filename}")

    def save_to_csv(self, data, filename):
        """Save data to CSV file"""
        if not data:
            logger.warning("No data to save to CSV")
            return
            
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        logger.info(f"Data saved to {filename}")

def main():
    parser = argparse.ArgumentParser(description='Scrape car cover listings from OLX')
    parser.add_argument('--format', choices=['json', 'csv', 'both'], default='both',
                      help='Output format (json, csv, or both)')
    parser.add_argument('--pages', type=int, default=1,
                      help='Maximum number of pages to scrape')
    args = parser.parse_args()
    
    logger.info("Starting stealthy OLX scraper")
    logger.info(f"Will scrape up to {args.pages} page(s) and save as {args.format}")
    
    start_time = time.time()
    
    scraper = StealthyScraper()
    results = scraper.scrape_search_results(max_pages=args.pages)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if args.format in ['json', 'both']:
        json_filename = f"olx_car_covers_{timestamp}.json"
        scraper.save_to_json(results, json_filename)
        
    if args.format in ['csv', 'both']:
        csv_filename = f"olx_car_covers_{timestamp}.csv"
        scraper.save_to_csv(results, csv_filename)
    
    elapsed_time = time.time() - start_time
    logger.info(f"Successfully scraped {len(results)} car cover listings from OLX in {elapsed_time:.2f} seconds")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user. Exiting gracefully.")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
