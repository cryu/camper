from mongogogo import *
import datetime

__all__=["Barcamp", "BarcampSchema", "Barcamps"]

class BaseError(Exception):
    """base class for exceptions"""

    def __init__(self, msg):
        """initialize the error with a message"""
        self.msg = msg

class WorkflowError(BaseError):
    """error in workflow e.g. transition not allowed"""

    def __init__(self, msg = u"Transition nicht erlaubt" , old_state = None, new_state = None):
        """initialize the error with a message"""
        self.msg = msg
        self.old_state = old_state
        self.new_state = new_state

    def __str__(self):
        """return a printable representation"""
        return """<WorkflowError: %s (old=%s, new=%s)>""" %(self.msg, self.old_state, self.new_state)



class Location(Schema):
    """a location described by name, lat and long"""
    name = String()
    street = String()
    city = String()
    zip = String()
    country = String()
    url = String()
    phone = String()
    email = String()
    description = String()

    lat = Float()
    lng = Float()

class Sponsor(Schema):
    """a location described by name, lat and long"""
    logo = String(required=True) # asset id
    name = String(required=True)
    url = String(required=True)

class BlogLinkSchema(Schema):
    """a link to a blog for documentation"""
    title = String(required = True)
    url = String(required = True)
    user_id = String(required = True)

class EventSchema(Schema):
    """a sub schema describing one event"""
    name                = String(required=True)
    description         = String(required=True)
    start_date          = DateTime()
    end_date            = DateTime()
    location            = Location()
    participants        = List(String()) # TODO: ref
    waiting_list        = List(String()) # TODO: ref

class BarcampSchema(Schema):
    """main schema for a barcamp holding all information about core data, events etc."""

    created             = DateTime()
    updated             = DateTime()
    created_by          = String() # TODO: should be ref to user
    workflow            = String(required = True, default = "created") 
    
    # base data
    name                = String(required = True)
    description         = String(required = True)
    slug                = String(required = True)
    registration_date   = Date() # date when the registration starts
    start_date          = Date()
    end_date            = Date()
    location            = Location()
    size                = Integer(default = 0) # amount of people allowed
    twitter             = String() # only the username
    hashtag             = String() 
    gplus               = String() 
    homepage            = String() # URL
    twitterwall         = String() # URL
    fbAdminId           = String() # optional admin id for facebook use

    # documentation
    planning_pad        = String() # ID of the planning etherpad
    documentation_pad   = String() # ID of the pad for documentation
    planning_pad_public = Boolean(default = False)
    blogposts           = List(BlogLinkSchema())

    # user related
    admins              = List(String()) # TODO: ref
    invited_admins      = List(String()) # list of invited admins who have not yet accepted TODO: ref 
    subscribers         = List(String()) # TODO: ref

    # events
    events              = List(EventSchema())

    # image stuff
    logo                = String() # asset id
    sponsors            = List(Sponsor())


class Event(AttributeMapper):
    """wraps event data with a class to provider more properties etc."""

    @property
    def state(self):
        """returns the state of the event which can be one of

        planning -- the event has not started
        active -- the event is active
        finished -- the event has finished

        All of those depend on the date which will be checked in here. 

        We only check for days, not timestamps, so if an event starts at 10am it still
        is supposed to be active for the whole day.
        """

        # convert everthing to dates without time
        today = datetime.date.today()
        start = self.start_date.date()
        end = self.end_date.date()

        if today < start:
            return "planning"
        if today > end:
            return "finished"
        return "active"


class Barcamp(Record):

    schema = BarcampSchema()
    _protected = ['schema', 'collection', '_protected', '_schemaless', 'default_values', 'admin_users', 'workflow_states', 'initial_workflow_state']
    initial_workflow_state = "created"
    default_values = {
        'created'       : datetime.datetime.utcnow,
        'updated'       : datetime.datetime.utcnow,
        'location'      : {},
        'workflow'      : "created",
        'events'        : [],
        'planning_pad_public'        : False,
    }

    workflow_states = {
        'created'       : ['public', 'deleted', 'canceled'],
        'public'        : ['registration', 'deleted', 'canceled'],
        'registration'  : ['deleted', 'canceled'],
        'canceled'      : ['deleted'],
    }

    def set_workflow(self, new_state):
        """set the workflow to a new state"""
        old_state = self.workflow                                                                                                                                                      
        if old_state is None:
            old_state = self.initial_workflow_state
        allowed_states = self.workflow_states[old_state]

        # check if transition is allowed
        if hasattr(self, "check_wf_"+new_state):
            m = getattr(self, "check_wf_"+new_state)
            if not m(old_state = old_state): # this should raise WorkflowError if not allowed otherwise return True
                raise WorkflowError(old_state = old_state, new_state = new_state) # fallback

        if new_state not in allowed_states:
            raise WorkflowError(old_state = old_state, new_state = new_state)

        # Trigger
        if hasattr(self, "on_wf_"+new_state):
            m = getattr(self, "on_wf_"+new_state)
            m(old_state = old_state)
        self.workflow = new_state
   
    @property
    def public(self):
        """return whether the barcamp is public or not"""
        return self.workflow in ['public', 'registration', 'canceled']

    def add_admin(self, user):
        """add a new admin to the invited admins list"""
        self.admins.append(unicode(user._id))

    def remove_admin_by_id(self, user_id):
        """remove an admin from the list of admins but only if the list is not empty then and the
        creator of the barcamp is still on it."""
        if unicode(user_id) == self.created_by:
            return
        if len(self.admins)<2:
            return
        self.admins.remove(unicode(user_id))

    def activate_admin(self, user):
        """activate an admin by moving from the invited to the actual list"""
        if user._id in self.invited_admins:
            self.invited_admins.remove(user._id)
            if user._id not in self.admins:
                self.admins.append(unicode(user._id))

    @property
    def admin_users(self):
        """return a list of user objects of the admin users"""
        ub = self._collection.md.app.module_map.userbase
        return list(ub.get_users_by_ids(self.admins))

    @property
    def subscriber_users(self):
        """return a list of user objects of the subscribed users"""
        ub = self._collection.md.app.module_map.userbase
        return list(ub.get_users_by_ids(self.subscribers))

    @property
    def participant_users(self):
        """return a list of user objects of the participants"""
        ub = self._collection.md.app.module_map.userbase
        return list(ub.get_users_by_ids(self.event.participants))

    @property
    def waitinglist_users(self):
        """return a list of user objects of the people on the waitinglist"""
        ub = self._collection.md.app.module_map.userbase
        return list(ub.get_users_by_ids(self.event.waiting_list))

    @property
    def event(self):
        """returns the main event object or None in case there is no event"""
        if self.events == []:
            return None
        return Event(self.events[0])

    def get_events(self):
        """return the events wrapped in the ``Event`` class"""
        return [Event(e) for e in self.events]

    @property
    def state(self):
        """the same as the event state which we compute here for the main event.
        If multiple events are possible in the future then this will check all of the events

        If no event is present, ``planning`` will be returned.
        """

        if self.event is None:
            return "planning"
        return self.event.state

    def subscribe(self, user):
        """subscribe a user to the barcamp"""
        uid = unicode(user._id)
        if uid not in self.subscribers:
            self.subscribers.append(uid)
        self.put()

    def unsubscribe(self, user):
        """unsubscribe a user from the barcamp"""
        uid = unicode(user._id)
        if uid in self.subscribers:
            self.subscribers.remove(uid)
        self.put()
        

class Barcamps(Collection):
    
    data_class = Barcamp

    def by_slug(self, slug):
        """find a barcamp by slug"""
        return self.find_one({'slug' : slug})

    def before_serialize(self, obj):
        """update or create our event information before it's saved"""
        if obj.events == []:
            event = {}
        else:
            event = obj.events[0]
        event.update({
            'name' : obj.name,
            'description' : obj.description,
            'start_date' : obj.start_date,
            'end_date' : obj.end_date,
            'location' : obj.location,
        })
        if obj.events == []:
            obj.events.append(event)
        else:
            obj.events[0] = event

        return obj

