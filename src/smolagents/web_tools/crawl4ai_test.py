import asyncio
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.processors.pdf import PDFCrawlerStrategy, PDFContentScrapingStrategy

async def pdf_test():
    # Initialize the PDF crawler strategy
    pdf_crawler_strategy = PDFCrawlerStrategy()

    # PDFCrawlerStrategy is typically used in conjunction with PDFContentScrapingStrategy
    # The scraping strategy handles the actual PDF content extraction
    pdf_scraping_strategy = PDFContentScrapingStrategy()
    run_config = CrawlerRunConfig(scraping_strategy=pdf_scraping_strategy)

    async with AsyncWebCrawler(crawler_strategy=pdf_crawler_strategy) as crawler:
        # Example with a remote PDF URL
        pdf_url = "https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf" # A public PDF from arXiv

        print(f"Attempting to process PDF: {pdf_url}")
        result = await crawler.arun(url=pdf_url, config=run_config)

        if result.success:
            print(f"Successfully processed PDF: {result.url}")
            print(f"Metadata Title: {result.metadata.get('title', 'N/A')}")
            # Further processing of result.markdown, result.media, etc.
            # would be done here, based on what PDFContentScrapingStrategy extracts.
            if result.markdown and hasattr(result.markdown, 'raw_markdown'):
                print(f"Extracted text (first 200 chars): {result.markdown.raw_markdown[:1000]}...")
            else:
                print("No markdown (text) content extracted.")
        else:
            print(f"Failed to process PDF: {result.error_message}")

async def web_test():
    async with AsyncWebCrawler() as crawler:
        config = CrawlerRunConfig(
            js_code=[
                "window.scrollTo(0, document.body.scrollHeight/2);",
                "window.scrollTo(0, document.body.scrollHeight);",
                "window.scrollTo(0, 0);",
            ],
            delay_before_return_html=2.5,
            page_timeout=5000
        )
        result = await crawler.arun(url="https://huntr.com/bounties/a6b521cf-258c-41c0-9edb-d8ef976abb2a", config=config)
        if result.success:
            print(f"Successfully processed URL: {result.url}")
            print(f"Metadata Title: {result.metadata.get('title', 'N/A')}")
            print(f"Extracted text: {result.markdown}")
        else:
            print(f"Failed to process URL: {result.error_message}")

if __name__ == "__main__":
    #asyncio.run(pdf_test())
    asyncio.run(web_test())