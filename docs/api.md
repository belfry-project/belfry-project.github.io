# Using the API

Everything in Belfry's web UI is also available in its REST API at `/api/v2/`. The
`awx.awx` collection and the `awx` CLI use the same API.

## API explorer on your instance

Every Belfry instance has an interactive API explorer (Swagger UI) at

```
https://<your Belfry server>/api/v2/docs/
```

It lists every endpoint of that instance, grouped by resource, with a filter box,
parameters, request bodies, responses and example values. With **Try it out** you send
real requests:

- If you are logged in to the web UI or the browsable API in the same browser, the
  explorer uses that session (and sends the CSRF token for POST, PUT, PATCH and DELETE).
- Otherwise, click **Authorize** and enter a username and password (HTTP basic
  authentication). The explorer forgets them when you reload or close the page.
- Requests run with the permissions of that user, like any API client: what the user
  may not see or change returns 403 or 404.

The same schema is available as ReDoc at `/api/v2/docs/redoc/` and as JSON at
`/api/v2/docs/schema/`. Swagger UI and ReDoc are served by Belfry itself; the pages
load nothing from other sites.

## Browsable API

Open `https://<your Belfry server>/api/` in a browser to browse the API page by page:
follow the links between resources, read the description of each endpoint, and send
POST, PUT, PATCH, OPTIONS and DELETE requests with the forms on the page. Responses are
shown as a collapsible JSON tree. The pages follow your browser's light or dark mode.

## Reference

The [API reference](https://belfry-project.github.io/docs/belfry/rest_api/api_ref.html)
in the Belfry manual documents the API of the latest release, with an introduction to
authentication, pagination and filtering (including `host_filter` for hosts). The
[schema.json](https://github.com/belfry-project/belfry/releases/latest/download/schema.json)
of each release is attached to its GitHub release.
