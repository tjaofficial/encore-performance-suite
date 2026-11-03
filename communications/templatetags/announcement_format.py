from django import template
from communications.announcement_richtext import display_announcement

register = template.Library()

@register.filter
def announcement_body(value):
    return display_announcement(value)
