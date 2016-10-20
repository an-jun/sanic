import re
from collections import defaultdict, namedtuple
from functools import lru_cache
from .config import Config
from .exceptions import NotFound, InvalidUsage

Route = namedtuple('Route', ['handler', 'methods', 'pattern', 'parameters'])
Parameter = namedtuple('Parameter', ['name', 'cast'])

REGEX_TYPES = {
    'string': (str, r'[^/]+'),
    'int': (int, r'\d+'),
    'number': (float, r'[0-9\\.]+'),
    'alpha': (str, r'[A-Za-z]+'),
}


def url_hash(url):
    return '/'.join(':' for s in url.split('/'))


class Router:
    """
    Router supports basic routing with parameters and method checks
    Usage:
        @sanic.route('/my/url/<my_parameter>', methods=['GET', 'POST', ...])
        def my_route(request, my_parameter):
            do stuff...

    Parameters will be passed as keyword arguments to the request handling
    function provided Parameters can also have a type by appending :type to
    the <parameter>.  If no type is provided, a string is expected.  A regular
    expression can also be passed in as the type

    TODO:
        This probably needs optimization for larger sets of routes,
        since it checks every route until it finds a match which is bad and
        I should feel bad
    """
    routes = None

    def __init__(self):
        self.routes = defaultdict(list)

    def add(self, uri, methods, handler):
        """
        Adds a handler to the route list
        :param uri: Path to match
        :param methods: Array of accepted method names.
        If none are provided, any method is allowed
        :param handler: Request handler function.
        When executed, it should provide a response object.
        :return: Nothing
        """

        # Dict for faster lookups of if method allowed
        if methods:
            methods = frozenset(methods)

        parameters = []

        def add_parameter(match):
            # We could receive NAME or NAME:PATTERN
            name = match.group(1)
            pattern = 'string'
            if ':' in name:
                name, pattern = name.split(':', 1)

            default = (str, pattern)
            # Pull from pre-configured types
            _type, pattern = REGEX_TYPES.get(pattern, default)
            parameters.append(Parameter(name=name, cast=_type))
            return '({})'.format(pattern)

        pattern_string = re.sub(r'<(.+?)>', add_parameter, uri)
        pattern = re.compile(r'^{}$'.format(pattern_string))

        route = Route(
            handler=handler, methods=methods, pattern=pattern,
            parameters=parameters)

        if parameters:
            uri = url_hash(uri)
        self.routes[uri].append(route)

    @lru_cache(maxsize=Config.ROUTER_CACHE_SIZE)
    def get(self, request):
        """
        Gets a request handler based on the URL of the request, or raises an
        error
        :param request: Request object
        :return: handler, arguments, keyword arguments
        """
        route = None
        url = request.url
        if url in self.routes:
            route = self.routes[url][0]
            match = route.pattern.match(url)
        else:
            for route in self.routes[url_hash(url)]:
                match = route.pattern.match(url)
                if match:
                    break
            else:
                raise NotFound('Requested URL {} not found'.format(url))

        if route.methods and request.method not in route.methods:
            raise InvalidUsage(
                'Method {} not allowed for URL {}'.format(
                    request.method, url), status_code=405)

        kwargs = {p.name: p.cast(value)
                  for value, p
                  in zip(match.groups(1), route.parameters)}
        return route.handler, [], kwargs
