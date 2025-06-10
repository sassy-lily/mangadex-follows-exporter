from requests import Response


class BaseClient:

    @staticmethod
    def _get_error(response: Response) -> RuntimeError:
        error = RuntimeError('Request failed.')
        error.add_note(f'URL: {response.request.url}')
        error.add_note(f'Status: {response.status_code}')
        error.add_note(f'Request: {response.request.body}')
        error.add_note(f'Response: {response.content}')
        return error
