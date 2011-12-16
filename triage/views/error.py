from pyramid.view import view_config
from pyramid.renderers import render_to_response
from pymongo.objectid import ObjectId
from pyramid.httpexceptions import HTTPFound, HTTPNotFound
from pyramid.security import authenticated_userid
from triage.helpers import get_errors, get_error_count
from pymongo import DESCENDING
from jinja2 import Markup

from triage.models import User
from triage.forms import CommentsSchema
from deform import Form, ValidationFailure
from time import time


@view_config(route_name='error_list', permission='authenticated')
def list(request):
    available_projects = request.registry.settings['projects']
    selected_project = get_selected_project(request)

    show = request.params.get('show', 'unseen')

    try:
        errors = get_errors(request, selected_project, show)
    except:
        errors = []

    params = {
        'errors': errors,
        'selected_project': selected_project,
        'available_projects': available_projects,
        'show': show,
        'get_error_count': lambda x: get_error_count(request, selected_project, x)
    }

    return render_to_response('error-list.html', params)


@view_config(route_name='error_view', permission='authenticated')
def view(request):
    available_projects = request.registry.settings['projects']
    selected_project = get_selected_project(request)

    error_id = request.matchdict['id']
    error = request.db[selected_project['collection']].find_one({'_id': ObjectId(error_id)})

    if not error:
        return HTTPNotFound()

    schema = CommentsSchema()
    form = Form(schema, buttons=('submit',))

    if 'submit' in request.POST:
        controls = request.POST.items()

        try:
            values = form.validate(controls)
            user = User.get_by_userid(request, authenticated_userid(request))

            comments = error.get('comments', [])
            comments.append({
                'name': user['email'],
                'comment': values['comment'],
                'timecreated': time()
            })
            error['comments'] = comments

            request.db[selected_project['collection']].save(error)

            url = request.route_url('error_view', project=selected_project['id'], id=error_id)
            return HTTPFound(location=url)
        except ValidationFailure, e:
            form_render = e.render()
    else:
        form_render = form.render()

    error['seen'] = True
    request.db[selected_project['collection']].save(error)

    other_errors = request.db['contest-errors'].find({
        'hash': error.get('hash', None)
    }).sort('timestamp', DESCENDING).limit(20)

    params = {
        'error': error,
        'other_errors': other_errors,
        'selected_project': selected_project,
        'available_projects': available_projects,
        'form': Markup(form_render),
        'user': User.get_by_userid(request, authenticated_userid(request)),
        'claimed': User.get_by_userid(request, error.get('claimed'))
    }

    try:
        template = 'error-view/' + str(error['language']).lower() + '.html'
        return render_to_response(template, params)
    except:
        template = 'error-view/generic.html'
        return render_to_response(template, params)


@view_config(route_name='error_toggle_claim', permission='authenticated')
def toggle_claim(request):
    selected_project = get_selected_project(request)

    error_id = request.matchdict['id']
    error = request.db[selected_project['collection']].find_one({'_id': ObjectId(error_id)})
    user = User.get_by_userid(request, authenticated_userid(request))

    if error and user:
        error['claimed'] = None if error.get('claimed') else user['_id']
        request.db[selected_project['collection']].save(error)

        url = request.route_url('error_view', project=selected_project['id'], id=error_id)
        return HTTPFound(location=url)

    return HTTPNotFound()


@view_config(route_name='error_toggle_hide')
def toggle_hide(request):
    selected_project = get_selected_project(request)

    error_id = request.matchdict['id']
    error = request.db[selected_project['collection']].find_one({'_id': ObjectId(error_id)})

    if error:
        error['hidden'] = not error.get('hidden', False)
        request.db[selected_project['collection']].save(error)

        url = request.route_url('error_list', project=selected_project['id'])
        return HTTPFound(location=url)

    return HTTPNotFound()


def get_selected_project(request):
    selected_project_key = request.matchdict['project']
    available_projects = request.registry.settings['projects']

    if selected_project_key in available_projects:
        return available_projects[selected_project_key]
    else:
        raise HTTPNotFound()
