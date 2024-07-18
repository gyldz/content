import datetime
import json
import uuid

from exchangelib.indexed_properties import PhoneNumber, PhysicalAddress

import EWSv2
import logging

import dateparser
import pytest
from exchangelib import Message, Mailbox, Contact, HTMLBody, Body
from EWSv2 import fetch_last_emails, get_message_for_body_type, parse_item_as_dict, parse_physical_address, get_attachment_name
from exchangelib.errors import UnauthorizedError, ErrorNameResolutionNoResults
from exchangelib import EWSDateTime, EWSTimeZone
from exchangelib.errors import ErrorInvalidIdMalformed, ErrorItemNotFound
import demistomock as demisto
from exchangelib.properties import ItemId


class TestNormalCommands:
    """

    """

    class MockClient:
        class MockAccount:
            def __init__(self):
                self.root = self
                self.walk_res = []
                self.all_res = ""
                self.contacts = self

            def walk(self):
                return self.walk_res

            def tree(self):
                return ""

            def all(self):
                return self.all_res

        def __init__(self):
            self.default_target_mailbox = ""
            self.client_id = ""
            self.client_secret = ""
            self.tenant_id = ""
            self.folder = ""
            self.is_public_folder = ""
            self.request_timeout = ""
            self.max_fetch = ""
            self.self_deployed = ""
            self.insecure = ""
            self.proxy = ""
            self.account = self.MockAccount()
            self.protocol = ""
            self.inbox = self.MockInbox()

        class MockInbox:
            class parent:
                def __init__(self):
                    self.children = ""

            def __init__(self):
                self.parent = self.parent()

        def get_folder_by_path(self, path, account=None, is_public=False):
            return ""


def test_keys_to_camel_case():
    assert EWSv2.keys_to_camel_case('this_is_a_test') == 'thisIsATest'
    # assert keys_to_camel_case(('this_is_a_test', 'another_one')) == ('thisIsATest', 'anotherOne')
    obj = {}
    obj['this_is_a_value'] = 'the_value'
    obj['this_is_a_list'] = []
    obj['this_is_a_list'].append('list_value')
    res = EWSv2.keys_to_camel_case(obj)
    assert res['thisIsAValue'] == 'the_value'
    assert res['thisIsAList'][0] == 'listValue'


def test_start_logging():
    EWSv2.start_logging()
    logging.getLogger().debug("test this")
    assert "test this" in EWSv2.log_stream.getvalue()


@pytest.mark.parametrize('since_datetime, expected_result',
                         [('', EWSDateTime.from_string('2021-05-23 13:18:14.901293+00:00'))])
def test_fetch_last_emails_first_fetch(mocker, since_datetime, expected_result):
    """
    Given:
        - First fetch timestamp - no last_run
    When:
        - Fetching last emails

    Then:
        - Verify datetime_received__gte is ten minutes earlier
    """

    class MockObject:
        def filter(self, datetime_received__gte=''):
            return MockObject2()

    class MockObject2:
        def filter(self):
            return MockObject2()

        def only(self, *args):
            return self

        def order_by(self, *args):
            return [Message(), Message(), Message(), Message(), Message()]

    client = TestNormalCommands.MockClient()
    mocker.patch.object(dateparser, 'parse', return_value=datetime.datetime(2021, 5, 23, 13, 18, 14, 901293,
                                                                            datetime.timezone.utc))
    mocker.patch.object(EWSv2, 'get_folder_by_path', return_value=MockObject())

    mocker.patch.object(MockObject, 'filter')

    fetch_last_emails(client, since_datetime=since_datetime)
    assert MockObject.filter.call_args[1].get('datetime_received__gte') == expected_result


@pytest.mark.parametrize('since_datetime, expected_result',
                         [('2021-05-23 21:18:14.901293+00:00',
                           '2021-05-23 21:18:14.901293+00:00')])
def test_fetch_last_emails_last_run(mocker, since_datetime, expected_result):
    """
    Given:
        - Not the first time fetching - last_run with a date
    When:
        - Fetching last emails

    Then:
        - Verify datetime_received__gte according to the datetime received
    """

    class MockObject:
        def filter(self, datetime_received__gte=''):
            return MockObject2()

    class MockObject2:
        def filter(self):
            return MockObject2()

        def only(self, *args):
            return self

        def order_by(self, *args):
            return [Message(), Message(), Message(), Message(), Message()]

    mocker.patch.object(EWSv2, 'get_folder_by_path', return_value=MockObject())
    mocker.patch.object(MockObject, 'filter')

    client = TestNormalCommands.MockClient()

    fetch_last_emails(client, since_datetime=since_datetime)
    assert MockObject.filter.call_args[1].get('datetime_received__gte') == expected_result


@pytest.mark.parametrize('limit, expected_result',
                         [(6, 5),
                          (2, 2),
                          (5, 5)])
def test_fetch_last_emails_limit(mocker, limit, expected_result):
    """
    Given:
        - Max fetch is 6
        - Max fetch is 2
        - Max fetch is 5

    When:
        - Fetching last emails - need to make sure to return emails according to the max_fetch param.

    Then:
        - Return 5 emails (Cause we only have 5 emails)
        - Return 2 emails
        - Return 5 emails
    """

    class MockObject:
        def filter(self, datetime_received__gte=''):
            return MockObject2()

    class MockObject2:
        def filter(self):
            return MockObject2()

        def only(self, *args):
            return self

        def order_by(self, *args):
            return [Message(), Message(), Message(), Message(), Message()]

    mocker.patch.object(EWSv2, 'get_folder_by_path', return_value=MockObject())
    EWSv2.MAX_FETCH = limit
    client = TestNormalCommands.MockClient()

    x = fetch_last_emails(client, since_datetime='since_datetime')
    assert len(x) == expected_result


def test_fetch_last_emails_fail(mocker):
    """
    This UT is added due to the following issue: XSUP-28730
    where an ErrorMimeContentConversionFailed exception is raised if there was a corrupt object in the stream of
    results returned from the fetch process (exchangelib module behavior).
    If such exception is encountered, it would be handled internally so that the integration would not crash.

    Given:
        - First exception raised is ErrorMimeContentConversionFailed
        - Second exception raised is ValueError

    When:
        - Iterating over mail objects when fetching last emails

    Then:
        - Catch ErrorMimeContentConversionFailed, print relevant debug message
          for encountered corrupt object and continue iteration to next object
        - Catch ValueError, and raise it forward
    """
    from EWSv2 import ErrorMimeContentConversionFailed

    class MockObject:
        def filter(self, datetime_received__gte=''):
            return MockObject2()

    class MockObject2:
        def filter(self):
            return MockObject2()

        def only(self, *args):
            return self

        def order_by(self, *args):
            return [Message(), Message(), Message(), Message(), Message()]

    mocker.patch.object(EWSv2, 'get_folder_by_path', return_value=MockObject())
    EWSv2.MAX_FETCH = 1
    client = TestNormalCommands.MockClient()

    mocker.patch('EWSv2.isinstance', side_effect=[ErrorMimeContentConversionFailed(AttributeError()), ValueError()])

    with pytest.raises(ValueError) as e:
        fetch_last_emails(client, since_datetime='since_datetime')
        assert str(e) == 'Got an error when pulling incidents. You might be using the wrong exchange version.'


def test_fetch_last_emails_object_stream_behavior(mocker):
    """
    This UT is added due to the following issue: XSUP-28730
    where an ErrorMimeContentConversionFailed exception is raised if there was a corrupt object in the stream of
    results returned from the fetch process (exchangelib module behavior).
    If such exception is encountered, it would be handled internally so that the integration would not crash

    Given:
        - A stream of 3 fetched objects, where objects in indexes 0,2 are valid message objects
          and the object in index 1 is an exception object (corrupt object)

    When:
        - Iterating over mail objects when fetching last emails

    Then:
        - Iterate over the fetched objects
        - Catch the corrupt object object, print relevant debug message
          and continue iteration to next object
        - Assert only valid objects are in the result
    """
    from EWSv2 import ErrorMimeContentConversionFailed

    class MockObject:
        def filter(self, datetime_received__gte=''):
            return MockObject2()

    class MockObject2:
        def filter(self):
            return MockObject2()

        def only(self, *args):
            return self

        def order_by(self, *args):
            return [Message(), Message(), Message()]

    mocker.patch.object(EWSv2, 'get_folder_by_path', return_value=MockObject())
    EWSv2.MAX_FETCH = 3
    client = TestNormalCommands.MockClient()

    mocker.patch('EWSv2.isinstance', side_effect=[True, ErrorMimeContentConversionFailed(AttributeError()), True])

    x = fetch_last_emails(client, since_datetime='since_datetime')
    assert len(x) == 2


def test_dateparser():
    """Test that dateparser works fine. See: https://github.com/demisto/etc/issues/39240 """
    now = datetime.datetime.now()
    res = dateparser.parse(EWSv2.FETCH_TIME)
    assert res is not None
    assert res < now


MESSAGES = [
    Message(subject='message1',
            message_id='message1',
            text_body='Hello World',
            body='message1',
            datetime_received=EWSDateTime(2021, 7, 14, 13, 00, 00, tzinfo=EWSTimeZone('UTC')),
            datetime_sent=EWSDateTime(2021, 7, 14, 13, 00, 00, tzinfo=EWSTimeZone('UTC')),
            datetime_created=EWSDateTime(2021, 7, 14, 13, 00, 00, tzinfo=EWSTimeZone('UTC'))
            ),
    Message(subject='message2',
            message_id='message2',
            text_body='Hello World',
            body='message2',
            datetime_received=EWSDateTime(2021, 7, 14, 13, 9, 00, tzinfo=EWSTimeZone('UTC')),
            datetime_sent=EWSDateTime(2021, 7, 14, 13, 9, 00, tzinfo=EWSTimeZone('UTC')),
            datetime_created=EWSDateTime(2021, 7, 14, 13, 9, 00, tzinfo=EWSTimeZone('UTC'))
            ),
    Message(subject='message3',
            message_id='message3',
            text_body='Hello World',
            body='message3',
            datetime_received=EWSDateTime(2021, 7, 14, 13, 9, 00, tzinfo=EWSTimeZone('UTC')),
            datetime_sent=EWSDateTime(2021, 7, 14, 13, 9, 00, tzinfo=EWSTimeZone('UTC')),
            datetime_created=EWSDateTime(2021, 7, 14, 13, 9, 00, tzinfo=EWSTimeZone('UTC'))
            ),
    Message(subject='message4',
            message_id='message4',
            text_body='Hello World',
            body='message4',
            datetime_received=EWSDateTime(2021, 7, 14, 13, 10, 00, tzinfo=EWSTimeZone('UTC')),
            datetime_sent=EWSDateTime(2021, 7, 14, 13, 9, 00, tzinfo=EWSTimeZone('UTC')),
            datetime_created=EWSDateTime(2021, 7, 14, 13, 11, 00, tzinfo=EWSTimeZone('UTC'))
            ),
]
CASE_FIRST_RUN_NO_INCIDENT = (
    {},
    [],
    {'lastRunTime': None, 'folderName': 'Inbox', 'ids': [], 'errorCounter': 0}
)
CASE_FIRST_RUN_FOUND_INCIDENT = (
    {},
    MESSAGES[:1],
    {'lastRunTime': '2021-07-14T13:00:00Z', 'folderName': 'Inbox', 'ids': ['message1'], 'errorCounter': 0}
)
CASE_SECOND_RUN_FOUND_ONE_INCIDENT = (
    {'lastRunTime': '2021-07-14T12:59:17Z', 'folderName': 'Inbox', 'ids': []}, MESSAGES[:1],
    {'lastRunTime': '2021-07-14T13:00:00Z', 'folderName': 'Inbox', 'ids': ['message1'], 'errorCounter': 0})
CASE_SECOND_RUN_FOUND_MORE_THAN_ONE_FIRST_RUN = (
    {'lastRunTime': '2021-07-14T13:05:17Z', 'folderName': 'Inbox', 'ids': ['message1']}, MESSAGES[0:3],
    {'lastRunTime': '2021-07-14T13:09:00Z', 'folderName': 'Inbox', 'ids': ['message2'], 'errorCounter': 0})
CASE_SECOND_RUN_FOUND_MORE_THAN_ONE_NEXT_RUN = (
    {'lastRunTime': '2021-07-14T13:09:00Z', 'folderName': 'Inbox', 'ids': ['message2']}, MESSAGES[1:3],
    {'lastRunTime': '2021-07-14T13:09:00Z', 'folderName': 'Inbox', 'ids': ['message2', 'message3'], 'errorCounter': 0})
CASE_SECOND_RUN_NO_INCIDENTS = (
    {'lastRunTime': '2021-07-14T12:59:17Z', 'folderName': 'Inbox', 'ids': ['message1']}, [],
    {'lastRunTime': '2021-07-14T12:59:17Z', 'folderName': 'Inbox', 'ids': ['message1'], 'errorCounter': 0})
CASE_SECOND_RUN_DIFFERENT_CREATED_RECEIVED_TIME = (
    {'lastRunTime': '2021-07-14T13:09:00Z', 'folderName': 'Inbox', 'ids': []}, MESSAGES[3:],
    {'lastRunTime': '2021-07-14T13:10:00Z', 'folderName': 'Inbox', 'ids': ['message4'], 'errorCounter': 0})
CASES = [
    CASE_FIRST_RUN_NO_INCIDENT,
    CASE_FIRST_RUN_FOUND_INCIDENT,
    CASE_SECOND_RUN_FOUND_ONE_INCIDENT,
    CASE_SECOND_RUN_FOUND_MORE_THAN_ONE_FIRST_RUN,
    CASE_SECOND_RUN_FOUND_MORE_THAN_ONE_NEXT_RUN,
    CASE_SECOND_RUN_NO_INCIDENTS,
    CASE_SECOND_RUN_DIFFERENT_CREATED_RECEIVED_TIME,
]


@pytest.mark.parametrize('current_last_run, messages, expected_last_run', CASES)
def test_last_run(mocker, current_last_run, messages, expected_last_run):
    """Check the fetch command.

    Given:
        - Last Run data including time and ids to be excluded.
    When:
        - Running fetch command.
    Then:
        - Validates the new Last Run new excluded IDs and last run time.
    """
    from EWSv2 import fetch_emails_as_incidents
    import demistomock as demisto

    class MockObject:
        def filter(self, datetime_received__gte=''):
            return MockObject2()

    class MockObject2:
        def filter(self):
            return MockObject2()

        def only(self, *args):
            return self

        def order_by(self, *args):
            return messages

    client = TestNormalCommands.MockClient()
    mocker.patch.object(EWSv2, 'get_folder_by_path', return_value=MockObject())
    mocker.patch.object(EWSv2, 'get_account', return_value='test_account')
    EWSv2.MAX_FETCH = 1
    last_run = mocker.patch.object(demisto, 'setLastRun')
    mocker.patch.object(demisto, 'getLastRun', return_value=current_last_run)
    fetch_emails_as_incidents(client, 'Inbox')
    assert last_run.call_args[0][0].get('lastRunTime') == expected_last_run.get('lastRunTime')
    assert set(last_run.call_args[0][0].get('ids')) == set(expected_last_run.get('ids'))


class MockItem:
    def __init__(self, item_id):
        self.id = item_id


class MockAccount:
    def __init__(self, primary_smtp_address="", error=401):
        self.primary_smtp_address = primary_smtp_address
        self.error = error

    @property
    def root(self):
        if self.error == 401:
            raise UnauthorizedError('Wrong username or password')
        if self.error == 404:
            raise Exception('Page not found')

    def fetch(self, ids):
        if isinstance(ids, type(map)):
            ids = list(ids)

        result = []

        for item in ids:
            item_id = item.id
            if item_id == '3':
                result.append(ErrorInvalidIdMalformed(value="malformed ID 3"))
            elif item_id == '4':
                result.append(ErrorItemNotFound(value="ID 4 was not found"))
            else:
                result.append(item_id)
        return result


def test_send_mail(mocker):
    """
    Given -
        to, subject and replyTo arguments to send an email.

    When -
        trying to send an email

    Then -
        verify the context output is returned correctly and that the 'to' and 'replyTo' arguments were sent
        as a list of strings.
    """
    from EWSv2 import send_email
    mocker.patch.object(EWSv2, 'Account', return_value=MockAccount(primary_smtp_address="test@gmail.com"))
    send_email_mocker = mocker.patch.object(EWSv2, 'send_email_to_mailbox', return_value=(''))
    results = send_email({'to': "test@gmail.com", 'subject': "test", 'replyTo': "test1@gmail.com"})
    assert send_email_mocker.call_args.kwargs.get('to') == ['test@gmail.com']
    assert send_email_mocker.call_args.kwargs.get('reply_to') == ['test1@gmail.com']
    assert results[0].get('Contents') == {
        'from': 'test@gmail.com', 'to': ['test@gmail.com'], 'subject': 'test', 'attachments': []
    }


def test_send_mail_with_from_arg(mocker):
    """
    Given -
        to, subject and replyTo arguments to send an email.

    When -
        trying to send an email

    Then -
        verify the context output is returned correctly and that the 'to' and 'replyTo' arguments were sent
        as a list of strings.
    """
    from EWSv2 import send_email
    mocker.patch.object(EWSv2, 'Account', return_value=MockAccount(primary_smtp_address="test@gmail.com"))
    send_email_mocker = mocker.patch.object(EWSv2, 'send_email_to_mailbox', return_value=('', [
        {'Contents': '', 'ContentsFormat': 'text', 'Type': 'png', 'File': 'image.png', 'FileID': '12345'}]))
    results = send_email({'to': "test@gmail.com", 'subject': "test", 'replyTo': "test1@gmail.com", "from": "somemail@what.ever"})
    assert send_email_mocker.call_args.kwargs.get('to') == ['test@gmail.com']
    assert send_email_mocker.call_args.kwargs.get('reply_to') == ['test1@gmail.com']
    assert results[0].get('Contents') == {
        'from': 'somemail@what.ever', 'to': ['test@gmail.com'], 'subject': 'test', 'attachments': []
    }


def test_send_mail_with_trailing_comma(mocker):
    """
    Given -
        a 'subject' which is 'test' and 'to' which is 'test@gmail.com,' (ending with a comma),

    When -
        trying to send an email

    Then -
        verify that the 'to' field was extracted correctly and that the trailing comma was handled.
    """
    from EWSv2 import send_email
    mocker.patch.object(EWSv2, 'Account', return_value=MockAccount(primary_smtp_address="test@gmail.com"))
    send_email_mocker = mocker.patch.object(EWSv2, 'send_email_to_mailbox', return_value=('', [
        {'Contents': '', 'ContentsFormat': 'text', 'Type': 'png', 'File': 'image.png', 'FileID': '12345'}]))
    results = send_email({'to': "test@gmail.com,", 'subject': "test"})
    assert send_email_mocker.call_args.kwargs.get('to') == ['test@gmail.com']
    assert results[0].get('Contents') == {
        'from': 'test@gmail.com', 'to': ['test@gmail.com'], 'subject': 'test', 'attachments': []
    }


@pytest.mark.parametrize(
    'item_ids, should_throw_exception', [
        (
            ['1'],
            False
        ),
        (
            ['1', '2'],
            False
        ),
        (
            ['1', '2', '3'],
            True
        ),
        (
            ['1', '2', '3', '4'],
            True
        ),
    ]
)
def test_get_items_from_mailbox(mocker, item_ids, should_throw_exception):
    """
    Given -
        Case A: single ID which is valid
        Case B: two IDs which are valid
        Case C: two ids which are valid and one id == 3 which cannot be found
        Case D: two ids which are valid and one id == 3 which cannot be found and one id == 4 which is malformed

    When -
        executing get_items_from_mailbox function

    Then -
        Case A: make sure the ID is returned successfully
        Case B: make sure that IDs are returned successfully
        Case C: make sure an exception is raised
        Case D: make sure an exception is raised
    """
    from EWSv2 import get_items_from_mailbox

    mocker.patch('EWSv2.Item', side_effect=[MockItem(item_id=item_id) for item_id in item_ids])

    if should_throw_exception:
        with pytest.raises(Exception):
            get_items_from_mailbox(MockAccount(), item_ids=item_ids)
    else:
        assert get_items_from_mailbox(MockAccount(), item_ids=item_ids) == item_ids


def test_categories_parse_item_as_dict():
    """
    Given -
        a Message with categories.

    When -
        running the parse_item_as_dict function.

    Then -
        verify that the categories were parsed correctly.
    """
    from EWSv2 import parse_item_as_dict

    message = Message(subject='message4',
                      message_id='message4',
                      text_body='Hello World',
                      body='message4',
                      datetime_received=EWSDateTime(2021, 7, 14, 13, 10, 00, tzinfo=EWSTimeZone('UTC')),
                      datetime_sent=EWSDateTime(2021, 7, 14, 13, 9, 00, tzinfo=EWSTimeZone('UTC')),
                      datetime_created=EWSDateTime(2021, 7, 14, 13, 11, 00, tzinfo=EWSTimeZone('UTC')),
                      categories=['Purple category', 'Orange category']
                      )

    return_value = parse_item_as_dict(message, False)
    assert return_value.get("categories") == ['Purple category', 'Orange category']


def test_list_parse_item_as_dict():
    """
    Given -
        a Message where effective rights is a list.

    When -
        running the parse_item_as_dict function.

    Then -
        verify that the object is parsed correctly.
    """
    from EWSv2 import parse_item_as_dict
    from exchangelib.properties import EffectiveRights

    message = Message(subject='message4',
                      message_id='message4',
                      text_body='Hello World',
                      body='message4',
                      datetime_received=EWSDateTime(2021, 7, 14, 13, 10, 00, tzinfo=EWSTimeZone('UTC')),
                      datetime_sent=EWSDateTime(2021, 7, 14, 13, 9, 00, tzinfo=EWSTimeZone('UTC')),
                      datetime_created=EWSDateTime(2021, 7, 14, 13, 11, 00, tzinfo=EWSTimeZone('UTC')),
                      effective_rights=[EffectiveRights(), EffectiveRights()]
                      )

    return_value = parse_item_as_dict(message, False)
    effetive_right_res = return_value.get("effective_rights")
    assert type(effetive_right_res) is list
    assert len(effetive_right_res) == 2


def test_parse_item_as_dict_with_empty_field():
    """
    Given -
        a Message where effective rights is None and other fields are false/empty strings.

    When -
        running the parse_item_as_dict function.

    Then -
        effective rights field was removed from response other empty\negative fields aren't.
    """
    from EWSv2 import parse_item_as_dict

    message = Message(subject='message4',
                      message_id='message4',
                      text_body='Hello World',
                      body='',
                      datetime_received=EWSDateTime(2021, 7, 14, 13, 10, 00, tzinfo=EWSTimeZone('UTC')),
                      datetime_sent=EWSDateTime(2021, 7, 14, 13, 9, 00, tzinfo=EWSTimeZone('UTC')),
                      datetime_created=EWSDateTime(2021, 7, 14, 13, 11, 00, tzinfo=EWSTimeZone('UTC')),
                      effective_rights=None,
                      is_read=False
                      )

    return_value = parse_item_as_dict(message, False)
    assert 'effective_rights' not in return_value
    assert return_value['body'] == ''
    assert return_value['is_read'] is False


def test_get_entry_for_object_empty():
    from EWSv2 import get_entry_for_object
    obj = {}
    assert get_entry_for_object("test", "keyTest", obj) == "There is no output results"


def test_get_entry_for_object():
    from EWSv2 import get_entry_for_object
    obj = {"a": 1, "b": 2}
    assert get_entry_for_object("test", "keyTest", obj)['HumanReadable'] == '### test\n|a|b|\n|---|---|\n| 1 | 2 |\n'


def test_get_time_zone(mocker):
    """
    When -
        trying to send/reply an email we check the XOSAR user time zone

    Then -
        verify that info returns
    """
    from EWSv2 import get_time_zone
    mocker.patch.object(demisto, 'callingContext', new={'context': {'User': {'timeZone': 'Asia/Jerusalem'}}})
    results = get_time_zone()
    assert results.key == 'Asia/Jerusalem'


def test_resolve_names_command_no_contact(mocker):
    """
        Given:
            Calling resolve_name_command
        When:
            Only a Mailbox is returned
        Then:
            The results are displayed correctly without FullContactInfo
    """
    from EWSv2 import resolve_name_command
    protocol = mocker.Mock()
    email = '1234@demisto.com'
    protocol.resolve_names.return_value = [Mailbox(email_address=email)]
    result = resolve_name_command({'identifier': 'someIdentifier'}, protocol)
    assert email in result.get('HumanReadable')
    assert email == list(result.get('EntryContext').values())[0][0].get('email_address')
    assert not list(result.get('EntryContext').values())[0][0].get('FullContactInfo')


def test_resolve_names_command_with_contact(mocker):
    """
        Given:
            Calling resolve_name_command
        When:
            A Mailbox, Contact tuple is returned
        Then:
            The results are displayed correctly with FullContactInfo
    """
    from EWSv2 import resolve_name_command
    protocol = mocker.Mock()
    email = '1234@demisto.com'
    number_label = 'Bussiness2'
    phone_numbers = [PhoneNumber(label=number_label, phone_number='+972 058 000 0000'),
                     PhoneNumber(label='Bussiness', phone_number='+972 058 000 0000')]
    protocol.resolve_names.return_value = [(Mailbox(email_address=email), Contact(phone_numbers=phone_numbers))]
    result = resolve_name_command({'identifier': 'someIdentifier'}, protocol)
    assert email in result.get('HumanReadable')
    context_output = list(result.get('EntryContext').values())[0][0]
    assert email == context_output.get('email_address')

    assert any(number.get('label') == number_label for number in context_output.get('FullContactInfo').get('phoneNumbers'))


def test_resolve_names_command_no_result(mocker):
    """
        Given:
            Calling resolve_name_command
        When:
            ErrorNameResolutionNoResults is returned
        Then:
            A human readable string is returned
    """
    from EWSv2 import resolve_name_command
    protocol = mocker.Mock()
    protocol.resolve_names.return_value = [ErrorNameResolutionNoResults(value='No results')]
    result = resolve_name_command({'identifier': 'someIdentifier'}, protocol)
    assert result == 'No results were found.'


def test_parse_phone_number():
    """
        Given: A filled phone number and a Phonenumber with no backing number
        When: Calling parse_phone_number
        Then: Only get the context object when the phpone_number is populated
    """
    good_number = EWSv2.parse_phone_number(PhoneNumber(label='123', phone_number='123123123'))
    assert good_number.get('label')
    assert good_number.get('phone_number')
    assert not EWSv2.parse_phone_number(PhoneNumber(label='123'))


def test_switch_hr_headers():
    """
           Given: A context object
           When: switching headers using a given header switch dict
           Then: The keys that are present are switched
       """
    assert (EWSv2.switch_hr_headers(
        {'willswitch': '1234', 'wontswitch': '111', 'alsoswitch': 5555},
        {'willswitch': 'newkey', 'alsoswitch': 'annothernewkey', 'doesnt_exiest': 'doesnt break'})
        == {'annothernewkey': 5555, 'newkey': '1234', 'wontswitch': '111'})


@pytest.mark.parametrize('input, output', [
    ('John Smith', 'John Smith'),
    ('SomeName', 'SomeName'),
    ('sip:test@test.com', 'sip:test@test.com'),
    ('hello@test.com', 'smtp:hello@test.com')
])
def test_format_identifier(input, output):
    """
           Given: several inputs with and without prefixes, that are or arent mails
           When: calling format_identifier
           Then: Only mails without a prefix have smtp appended
       """
    assert EWSv2.format_identifier(input) == output


def test_get_message_for_body_type_no_body_type_with_html_body():
    body = "This is a plain text body"
    html_body = "<p>This is an HTML body</p>"
    result = get_message_for_body_type(body, None, html_body)
    assert isinstance(result[0], HTMLBody)
    assert result[0] == HTMLBody(html_body)


def test_get_message_for_body_type_no_body_type_with_html_body_and_image(mocker):
    from exchangelib import FileAttachment
    mocker.patch.object(uuid, 'uuid4', return_value='123456')
    body = "This is a plain text body"
    html_body = '<p>This is an HTML body</p><p><img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA"/></p>'
    result = get_message_for_body_type(body, None, html_body)
    assert isinstance(result[0], HTMLBody)
    assert isinstance(result[1][0], FileAttachment)
    assert result[0] == HTMLBody('<p>This is an HTML body</p><p><img src="cid:image0_123456_123456"/></p>')


def test_get_message_for_body_type_no_body_type_with_no_html_body():
    body = "This is a plain text body"
    result = get_message_for_body_type(body, None, None)
    assert isinstance(result[0], Body)
    assert result[0] == Body(body)


def test_get_message_for_body_type_html_body_type_with_html_body():
    body = "This is a plain text body"
    html_body = "<p>This is an HTML body</p>"
    result = get_message_for_body_type(body, 'html', html_body)
    assert isinstance(result[0], HTMLBody)
    assert result[0] == HTMLBody(html_body)


def test_get_message_for_body_type_text_body_type_with_html_body():
    body = "This is a plain text body"
    html_body = "<p>This is an HTML body</p>"
    result = get_message_for_body_type(body, 'text', html_body)
    assert isinstance(result[0], Body)
    assert result[0] == Body(body)


def test_get_message_for_body_type_html_body_type_with_no_html_body():
    body = "This is a plain text body"
    result = get_message_for_body_type(body, 'html', None)
    assert isinstance(result[0], Body)
    assert result[0] == Body(body)


def test_get_message_for_body_type_text_body_type_with_no_html_body():
    body = "This is a plain text body"
    result = get_message_for_body_type(body, 'text', None)
    assert isinstance(result[0], Body)
    assert result[0] == Body(body)


def test_get_message_for_body_type_text_body_type_with_html_body_no_body():
    """
    Given: html_body, no body, the default 'text' as body_type.
    When: Constructing the message body.
    Then: Assert that the result is an html body.
    """
    html_body = "<p>This is an HTML body</p>"
    result = get_message_for_body_type('', 'text', html_body)
    assert isinstance(result[0], HTMLBody)
    assert result[0] == HTMLBody(html_body)


def test_parse_physical_address():
    assert parse_physical_address(PhysicalAddress(city='New York',
                                                  country='USA',
                                                  label='SomeLabel',
                                                  state='NY',
                                                  street='Broadway Ave.',
                                                  zipcode=10001)) == {'city': 'New York',
                                                                      'country': 'USA',
                                                                      'label': 'SomeLabel',
                                                                      'state': 'NY',
                                                                      'street': 'Broadway Ave.',
                                                                      'zipcode': 10001}


def test_parse_item_as_dict_return_json_serializable():
    """
    Given:
        - A message with cc_recipients with an object that includes a non-serializable object (ItemId).
    When:
        - Calling parse_item_as_dict

    Then:
        - Verify that the received dict is json serializable,
        and that the ItemId appears both in the received dict and the json serialized object.
    """
    item = Message(cc_recipients=[Mailbox(item_id=ItemId(id='id123', changekey='change'))])
    item_as_dict = parse_item_as_dict(item, None)
    item_as_json = json.dumps(item_as_dict, ensure_ascii=False)
    assert isinstance((item_as_dict.get("cc_recipients", [])[0]).get("item_id"), dict)
    assert '"item_id": {"id": "id123", "changekey": "change"}' in item_as_json


@pytest.mark.parametrize("attachment_name, content_id, attachment_id, expected_result", [
    pytest.param('image1.png', "", '123', "123-attachmentName-image1.png"),
    pytest.param('image1.png', '123', '456', "123-attachmentName-image1.png"),
    pytest.param('image1.png', None, '456', "456-attachmentName-image1.png"),

])
def test_get_attachment_name(attachment_name, content_id, attachment_id, expected_result):
    assert get_attachment_name(attachment_name=attachment_name, content_id=content_id,
                               attachment_id=attachment_id) == expected_result
