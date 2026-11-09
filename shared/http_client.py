import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
from opentelemetry import propagate, trace

tracer = trace.get_tracer(__name__)

def get_http_session(retries=3, backoff_factor=0.3, status_forcelist=(500, 502, 504)):
    """
    Returns a requests Session with a retry strategy.
    """
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

class HttpClient:
    def __init__(self, base_url: str = "", timeout: float = 15.0):
        self.base_url = base_url
        self.timeout = timeout
        self.session = get_http_session()
        self.logger = logging.getLogger(__name__)

    def get(self, endpoint: str, params: dict = None, **kwargs):
        from urllib.parse import urljoin
        url = urljoin(self.base_url, endpoint)
        
        # Inject trace context into headers
        headers = kwargs.get('headers', {})
        propagate.inject(headers)
        kwargs['headers'] = headers

        timeout = kwargs.pop('timeout', self.timeout)

        with tracer.start_as_current_span("http_get", attributes={"http.url": url}) as span:
            try:
                response = self.session.get(url, params=params, timeout=timeout, **kwargs)
                span.set_attribute("http.status_code", response.status_code)
                response.raise_for_status()
                return response
            except Exception as e:
                self.logger.error(f"HTTP GET failed: {url} - {str(e)}")
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, description=str(e)))
                raise

    def post(self, endpoint: str, json: dict = None, **kwargs):
        from urllib.parse import urljoin
        url = urljoin(self.base_url, endpoint)
        
        # Inject trace context into headers
        headers = kwargs.get('headers', {})
        propagate.inject(headers)
        kwargs['headers'] = headers

        timeout = kwargs.pop('timeout', self.timeout)

        with tracer.start_as_current_span("http_post", attributes={"http.url": url}) as span:
            try:
                response = self.session.post(url, json=json, timeout=timeout, **kwargs)
                span.set_attribute("http.status_code", response.status_code)
                response.raise_for_status()
                return response
            except Exception as e:
                self.logger.error(f"HTTP POST failed: {url} - {str(e)}")
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, description=str(e)))
                raise

