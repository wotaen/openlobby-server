import graphene
from django.db.models import Count, Q
from graphene import relay

from . import types
from .paginator import Paginator
from .sanitizers import extract_text
from .. import search
from ..models import OpenIdClient
from ..models import User, Report

AUTHOR_SORT_LAST_NAME_ID = 1
AUTHOR_SORT_TOTAL_REPORTS_ID = 2

REPORT_SORT_DATE_ID = 'date'
REPORT_SORT_PUBLISHED_ID = 'published'
REPORT_SORT_RELEVANCE_ID = '_score'


class AuthorSortEnum(graphene.Enum):
    LAST_NAME = AUTHOR_SORT_LAST_NAME_ID
    TOTAL_REPORTS = AUTHOR_SORT_TOTAL_REPORTS_ID

    class Meta:
        description = 'Sort by field.'


class ReportSortEnum(graphene.Enum):
    DATE = REPORT_SORT_DATE_ID
    PUBLISHED = REPORT_SORT_PUBLISHED_ID
    RELEVANCE = REPORT_SORT_RELEVANCE_ID

    class Meta:
        description = 'Sort by field.'


class AuthorsConnection(relay.Connection):
    total_count = graphene.Int()

    class Meta:
        node = types.Author


class SearchReportsConnection(relay.Connection):
    total_count = graphene.Int()

    class Meta:
        node = types.Report


def _get_authors_cache(ids):
    authors = User.objects.filter(id__in=ids) \
        .annotate(total_reports=Count('report', filter=Q(report__is_draft=False)))
    return {a.id: types.Author.from_db(a) for a in authors}


class Query:
    highlight_help = ('Whether search matches should be marked with tag <mark>.'
                      ' Default: false')

    node = relay.Node.Field()
    authors = relay.ConnectionField(
        AuthorsConnection,
        description='List of Authors. Returns first 10 nodes if pagination is not specified.',
        sort=AuthorSortEnum(),
        reversed=graphene.Boolean(default_value=False, description="Reverse order of sort")
    )
    search_reports = relay.ConnectionField(
        SearchReportsConnection,
        description='Fulltext search in Reports. Returns first 10 nodes if pagination is not specified.',
        query=graphene.String(description='Text to search for.'),
        highlight=graphene.Boolean(default_value=False, description=highlight_help),
        sort=ReportSortEnum(),
        reversed=graphene.Boolean(default_value=False, description="Reverse order of sort")
    )
    viewer = graphene.Field(types.User, description='Active user viewing API.')
    login_shortcuts = graphene.List(
        types.LoginShortcut,
        description='Shortcuts for login. Use with LoginByShortcut mutation.',
    )
    report_drafts = graphene.List(
        types.Report,
        description='Saved drafts of reports for Viewer.',
    )

    def resolve_authors(self, info, **kwargs):
        paginator = Paginator(**kwargs)

        total = User.objects.filter(is_author=True).count()

        authors = User.objects \
                      .sorted(**kwargs) \
                      .filter(is_author=True)[paginator.slice_from:paginator.slice_to]

        page_info = paginator.get_page_info(total)

        edges = []
        for i, author in enumerate(authors):
            cursor = paginator.get_edge_cursor(i + 1)
            node = types.Author.from_db(author)
            edges.append(AuthorsConnection.Edge(node=node, cursor=cursor))

        return AuthorsConnection(page_info=page_info, edges=edges, total_count=total)

    def resolve_search_reports(self, info, **kwargs):
        paginator = Paginator(**kwargs)
        query = kwargs.get('query', '')
        query = extract_text(query)
        params = {
            'highlight': kwargs.get('highlight'),
            'sort': kwargs.get('sort', REPORT_SORT_DATE_ID),
            'reversed': kwargs.get('reversed', False)
        }
        response = search.query_reports(query, paginator, **params)
        total = response.hits.total
        page_info = paginator.get_page_info(total)

        edges = []
        if len(response) > 0:
            authors = _get_authors_cache(ids=[r.author_id for r in response])
            for i, report in enumerate(response):
                cursor = paginator.get_edge_cursor(i + 1)
                node = types.Report.from_es(report, author=authors[report.author_id])
                edges.append(SearchReportsConnection.Edge(node=node, cursor=cursor))

        return SearchReportsConnection(page_info=page_info, edges=edges, total_count=total)

    def resolve_viewer(self, info, **kwargs):
        if info.context.user.is_authenticated:
            return types.User.from_db(info.context.user)
        else:
            return None

    def resolve_login_shortcuts(self, info, **kwargs):
        clients = OpenIdClient.objects.filter(is_shortcut=True).order_by('name')
        return [types.LoginShortcut.from_db(c) for c in clients]

    def resolve_report_drafts(self, info, **kwargs):
        if info.context.user.is_authenticated:
            drafts = Report.objects.filter(author=info.context.user, is_draft=True)
            return [types.Report.from_db(d) for d in drafts]
        else:
            return []
