from .models import DeletionRequest

def pending_deletions_count(request):
    if request.user.is_authenticated and (request.user.is_superuser or request.user.groups.filter(name='Admin').exists()):
        count = DeletionRequest.objects.filter(status='pending').count()
    else:
        count = 0
    return {'pending_deletions_count': count}