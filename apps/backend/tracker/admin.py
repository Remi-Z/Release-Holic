from django.contrib import admin
from django.db.models import Q

from .models import AdapterState, Claim, Creator, Edition, Event, EventRevision, ExternalIdentity, Franchise, IngestionRun, Relationship, SourceDocument, Unit, Work


class IdentityInline(admin.TabularInline):
    model = ExternalIdentity
    extra = 0


@admin.register(Work)
class WorkAdmin(admin.ModelAdmin):
    list_display = ["title", "kind", "franchise", "status"]
    list_filter = ["kind", "status"]
    search_fields = ["title", "original_title", "creators__name"]
    filter_horizontal = ["creators"]
    inlines = [IdentityInline]

    def save_model(self, request, obj, form, change):
        obj.curated_fields.update({"title": obj.title, "kind": obj.kind, "aliases": obj.aliases, "franchise_id": str(obj.franchise_id) if obj.franchise_id else None})
        for key in form.changed_data:
            if key in {'original_title', 'summary', 'language', 'status', 'canonical_url', 'image_url'}:
                obj.curated_fields[key] = getattr(obj, key)
        if 'creators' in form.changed_data:
            obj.curated_fields['creators'] = list(form.cleaned_data['creators'].values_list('name', flat=True))
        super().save_model(request, obj, form, change)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["title", "work", "kind", "precision", "verification", "lifecycle"]
    list_filter = ["kind", "verification", "lifecycle", "precision"]
    search_fields = ["title", "work__title"]
    readonly_fields = ['id', 'owner', 'scope_key', 'work', 'unit', 'edition', 'provider', 'external_key', 'published_at', 'observed_at', 'curated_fields', 'created_at', 'updated_at']

    def get_queryset(self, request):
        return super().get_queryset(request).filter(Q(owner__isnull=True) | Q(owner=request.user))

    def save_model(self, request, obj, form, change):
        from .services import event_payload

        previous = Event.objects.get(pk=obj.pk)
        before = event_payload(previous)
        after = event_payload(obj)
        for key in form.changed_data:
            if key in after:
                obj.curated_fields[key] = after[key]
        if 'scheduled_at' in form.changed_data or 'precision' in form.changed_data:
            for key in ['window_start', 'window_end']:
                obj.curated_fields[key] = after[key]
        super().save_model(request, obj, form, change)
        if before != after:
            EventRevision.objects.create(event=obj, actor=request.user, before=before, after=after, reason='Catalogue curator correction')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AdapterState)
class StateAdmin(admin.ModelAdmin):
    list_display = ["identity", "last_success_at", "last_checked_at", "last_error"]
    readonly_fields = [field.name for field in AdapterState._meta.fields]


@admin.register(IngestionRun)
class RunAdmin(admin.ModelAdmin):
    list_display = ["provider", "work", "status", "created_at", "finished_at"]
    readonly_fields = [field.name for field in IngestionRun._meta.fields]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(Q(owner__isnull=True) | Q(owner=request.user))


for model in [Franchise, Creator, Relationship, Unit, Edition]:
    admin.site.register(model)


class EvidenceAdmin(admin.ModelAdmin):
    readonly_fields = []

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if self.model is SourceDocument:
            return queryset.filter(Q(owner__isnull=True) | Q(owner=request.user))
        if self.model is Claim:
            return queryset.filter(Q(source__owner__isnull=True) | Q(source__owner=request.user))
        return queryset.filter(Q(event__owner__isnull=True) | Q(event__owner=request.user))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for model in [SourceDocument, Claim, EventRevision]:
    admin.site.register(model, EvidenceAdmin)

admin.site.site_header = "Release-Holic catalogue"
admin.site.site_title = "Release-Holic"
