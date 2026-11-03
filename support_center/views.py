from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse

from studios.models import StudioMembership

from .articles import ARTICLES, ARTICLE_BY_SLUG, CATEGORIES, CATEGORY_BY_SLUG


def _workspace_context(request):
    membership = None
    membership_id = request.session.get("encore_workspace_membership_id")
    if membership_id:
        membership = (
            StudioMembership.objects
            .select_related("studio")
            .filter(pk=membership_id, user=request.user, is_active=True)
            .first()
        )

    if membership is None:
        membership = (
            StudioMembership.objects
            .select_related("studio")
            .filter(user=request.user, is_active=True)
            .order_by("joined_at")
            .first()
        )

    if membership is None:
        return None

    return {
        "studio": membership.studio,
        "role": membership.role,
        "support_membership": membership,
    }


def _article_for_view(article, studio=None):
    item = dict(article)
    item["category_info"] = CATEGORY_BY_SLUG.get(article["category"], {})
    quick_link = dict(article.get("quick_link") or {})
    if quick_link.get("route"):
        kwargs = {"studio_slug": studio.slug} if quick_link.get("studio") and studio else {}
        try:
            quick_link["url"] = reverse(quick_link["route"], kwargs=kwargs)
        except NoReverseMatch:
            quick_link["url"] = ""
    item["quick_link"] = quick_link
    return item


@login_required
def home(request):
    workspace = _workspace_context(request)
    if workspace is None:
        return redirect("accounts:profile")

    category_cards = []
    for slug, name, description in CATEGORIES:
        category_articles = [article for article in ARTICLES if article["category"] == slug]
        category_cards.append({
            "slug": slug,
            "name": name,
            "description": description,
            "count": len(category_articles),
            "articles": category_articles,
        })

    search_index = [
        {
            "title": article["title"],
            "slug": article["slug"],
            "summary": article["summary"],
            "category": CATEGORY_BY_SLUG[article["category"]]["name"],
            "keywords": article.get("keywords", []),
            "url": reverse("support_center:article", kwargs={"slug": article["slug"]}),
        }
        for article in ARTICLES
    ]

    return render(
        request,
        "support_center/home.html",
        {
            **workspace,
            "category_cards": category_cards,
            "article_count": len(ARTICLES),
            "search_index": search_index,
        },
    )


@login_required
def article_detail(request, slug):
    workspace = _workspace_context(request)
    if workspace is None:
        return redirect("accounts:profile")

    article = ARTICLE_BY_SLUG.get(slug)
    if article is None:
        from django.http import Http404
        raise Http404("Support article not found.")

    article = _article_for_view(article, workspace["studio"])
    related = [
        _article_for_view(ARTICLE_BY_SLUG[related_slug], workspace["studio"])
        for related_slug in article.get("related", [])
        if related_slug in ARTICLE_BY_SLUG
    ]

    return render(
        request,
        "support_center/article_detail.html",
        {
            **workspace,
            "article": article,
            "related_articles": related,
        },
    )
