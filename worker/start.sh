cd /polyaxon/polyaxon
if [[ -z "${POLYAXON_SECURITY_CONTEXT_USER}" ]] || [[ -z "${POLYAXON_SECURITY_CONTEXT_GROUP}" ]]; then
    celery -A polyaxon $*
else
    ./create_user.sh
    chown -R polyaxon:polyaxon /polyaxon/logs/
    gosu polyaxon celery -A polyaxon $*
fi
