from django_cron import CronJobBase, Schedule
from mailfetcher.models import Mail, Eresource, Service, Thirdparty
from identity.models import Identity, ServiceThirdPartyEmbeds
import statistics
import tldextract
import traceback
import logging
from django.core.cache import cache
from django.conf import settings
from datetime import datetime
from django.db.models import Q
import requests

logger = logging.getLogger(__name__)
LONG_SEPERATOR = '##########################################################'

def create_summary_cache(force=False):
    site_params = cache.get('result_summary')
    if site_params is not None and not force:
        if not site_params['cache_dirty']:
            return
    print('Building cache for summary')
    all_services = Service.objects.all()
    approved_services = all_services.filter(hasApprovedIdentity=True)
    num_approved_services = approved_services.count()
    services_using_cookies = 0
    services_with_address_disclosure = 0
    services_embedding_third_parties = 0
    for service in approved_services:
        third_party_connections = ServiceThirdPartyEmbeds.objects.filter(service=service)
        if third_party_connections.filter(sets_cookie=True).exists():
            services_using_cookies += 1
        if third_party_connections.filter(leaks_address=True).exists():
            services_with_address_disclosure += 1
        tps = Thirdparty.objects.filter(name=service.url)
        if tps.exists():
            embeds = False
            for tp in tps:
                if third_party_connections.exclude(thirdparty=tp).exists():
                    embeds = True
            if embeds:
                services_embedding_third_parties += 1

    hosts = Thirdparty.objects.all()
    num_hosts = hosts.count()

    all_mails = Mail.objects.all()

    # Generate site params
    site_params = {
        # Num services (num services without approved identities)
        'num_services': all_services.count(),
        'num_approved_services': num_approved_services,
        # Num emails
        'num_received_mails': all_mails.count(),
        'percent_services_use_cookies': services_using_cookies / num_approved_services * 100,  # % of services set cookies. (on view and click?)
        'hosts_receiving_connections': num_hosts,  # Num third parties
        'percent_leak_address': services_with_address_disclosure / num_approved_services * 100,  # % of services leaking email address in any way
        'percent_embed_thirdparty': services_embedding_third_parties / num_approved_services * 100,  # % of services embed third parties
        'thirdparties_on_view': {  # third parties that are loaded by emails on view
            'min': -1,
            'max': -1,
            'median': -1,
            'mean': -1
        },
        'thirdparties_on_click': {  # third parties that are loaded by emails on click
            'min': -1,
            'max': -1,
            'median': -1,
            'mean': -1
        },
        'forwards_on_view': {  # forwards until reaching a resource per mail on view
            'min': -1,
            'max': -1,
            'median': -1,
            'mean': -1
        },
        'forwards_on_click': {  # forwards until reaching a resource per mail on click
            'min': -1,
            'max': -1,
            'median': -1,
            'mean': -1
        },
        'percent_personalised_urls': {  # % personalised urls per mail
            'min': -1,
            'max': -1,
            'median': -1,
            'mean': -1
        },
        'cache_dirty': False,
        'cache_timestamp': datetime.now().time()
    }
    # Cache the result
    cache.set('result_summary', site_params)


def create_third_party_cache(thirdparty, force=False):
    site_params = cache.get(thirdparty.derive_thirdparty_cache_path())
    if site_params is not None and not force:
        if not site_params['cache_dirty']:
            return
    print('Building cache for 3rd party: {}'.format(thirdparty.name))
    service_3p_conns = ServiceThirdPartyEmbeds.objects.filter(thirdparty=thirdparty)

    services = thirdparty.services.all()
    services = services.distinct()
    services_dict = {}
    for service in services:
        service_dict = {}
        embeds = service_3p_conns.filter(service=service)
        embeds_onview = embeds.filter(embed_type=ServiceThirdPartyEmbeds.ONVIEW)
        embeds_onclick = embeds.filter(embed_type=ServiceThirdPartyEmbeds.ONCLICK)
        # TODO check these
        service_dict['embed_as'] = list(embeds.values_list('embed_type', flat=True).distinct())
        service_dict['receives_address_view'] = embeds_onview.filter(leaks_address=True).exists()
        service_dict['receives_address_click'] = embeds_onclick.filter(leaks_address=True).exists()
        service_dict['sets_cookie'] = embeds.filter(sets_cookie=True).exists()
        service_dict['receives_identifiers'] = embeds.filter(receives_identifier=True).exists()

        services_dict[service] = service_dict

    receives_leaks = service_3p_conns.filter(leaks_address=True).exists()
    sets_cookies = service_3p_conns.filter(sets_cookie=True).exists()
    # Generate site params

    site_params = {
        'embed': thirdparty,
        'used_by_num_services': services.count(),
        # How many services embed this third party
        'services': services_dict,
        # services_dict = {
        #     service:{
        #         embed_as: list{embedtypes}
            #     'receives_address_view': Bool
            #     'receives_address_click': Bool
            #     'sets_cookie': Bool
        #         'receives_identifiers': Bool
        #     }
        # }
        'receives_address': receives_leaks,  # done
        # 'leak_algorithms': [],  # TODO list of algorithms used to leak the address to this third party
        'sets_cookies': sets_cookies,
        'cache_dirty': False,
        'cache_timestamp': datetime.now().time()
    }
    # Cache the result
    cache.set(thirdparty.derive_thirdparty_cache_path(), site_params)


def create_service_cache(service, force=False):
    site_params = cache.get(service.derive_service_cache_path())

    if site_params is not None and not force:
        if not site_params['cache_dirty']:
            print('Cache exists and not dirty.')
            return
    print('Building cache for service: {}'.format(service.name))
    # logger.debug("ServiceView.render_service: Cache miss", extra={'request': request, 'service_id': service.id})
    # Get all identities associated with this service
    idents = Identity.objects.filter(service=service)
    # Count how many identities have received spam
    third_party_spam = idents.filter(receives_third_party_spam=True).count()
    # Get all mails associated with this domain
    mails = Mail.objects.filter(identity__in=idents, identity__approved=True).distinct()
    # Count these eMails
    count_mails = mails.count()
    # Count eMail that have pairs from another identity
    # TODO How does this deal with situations with more than two identities?
    count_mult_ident_mails = mails.exclude(mail_from_another_identity=None).count()

    # Get all ereseource
    # resources = Eresource.objects.filter(mail__in=mails)
    # Get links
    # links = service.avg('a')
    # ...and connections
    # connections = service.avg('con')
    # Get known trackers
    # tracker = Thirdparty.objects.filter(eresource__in=resources, eresource__type='con').distinct()
    # Check for eMails leakage
    mail_leakage_resources = Eresource.objects.filter(mail_leakage__isnull=False, mail__in=service.mails())
    algos_string = ""
    algos = []
    if mail_leakage_resources.exists():
        for algorithms_list in mail_leakage_resources.values_list('mail_leakage').distinct():
            for algorithm in algorithms_list[0].split(', '):
                if algorithm in algos or algorithm == '':
                    continue
                algos.append(algorithm)
        algos_string = ', '.join(algos)

    # Get all identities associated with this service
    idents = Identity.objects.filter(service=service, approved=True)
    # Create data structure for frontend

    # All identities of the service
    # TODO Currently seems to not filter for content from approved messages only
    identities = Identity.objects.filter(service=service)
    emails = Mail.objects.filter(identity__in=identities, identity__approved=True).distinct()
    service_3p_conns = ServiceThirdPartyEmbeds.objects.filter(service=service)
    third_parties = service.thirdparties.all().distinct()

    cookies_per_mail = []
    for email in emails:
        cookies_per_mail.append(service_3p_conns.filter(mail=email, sets_cookie=True).count())
    try:
        cookies_set_mean = statistics.mean(cookies_per_mail)
    except:
        cookies_set_mean = 0

    third_parties_dict = {}

    counter_personalised_links = 0
    personalised_links = []
    personalised_anchor_links = []
    personalised_image_links = []
    num_embedded_links = []
    avg_personalised_image_links = 0
    avg_personalised_anchor_links = 0
    avg_num_embedded_links = 0
    ratio = 0
    for mail in service.mails():
        counter_personalised_links += 1
        all_static_eresources = Eresource.objects.filter(mail=mail). \
            filter(Q(type='a') | Q(type='link') | Q(type='img') | Q(type='script'))
        num_embedded_links.append(all_static_eresources.count())
        personalised_anchor_links.append(all_static_eresources.filter(type='a', personalised=True).count())
        personalised_image_links.append(all_static_eresources.filter(type='img', personalised=True).count())
        personalised_mails = all_static_eresources.filter(personalised=True)
        personalised_links.append(personalised_mails.count())
    if counter_personalised_links == 0:
        ratio = -1
    else:
        avg_num_embedded_links = statistics.mean(num_embedded_links)
        # TODO When does this happen?
        if avg_num_embedded_links == 0:
            ratio = 0
        else:
            ratio = statistics.mean(personalised_links) / avg_num_embedded_links
        avg_personalised_anchor_links = statistics.mean(personalised_anchor_links)
        avg_personalised_image_links = statistics.mean(personalised_image_links)

    for third_party in third_parties:
        # if 'pearl' in service.name:
        #     print ('')
        third_party_dict = {}
        embeds = service_3p_conns.filter(thirdparty=third_party)
        embeds_onview = embeds.filter(embed_type=ServiceThirdPartyEmbeds.ONVIEW)
        embeds_onclick = embeds.filter(embed_type=ServiceThirdPartyEmbeds.ONCLICK)
        third_party_dict['embed_as'] = list(embeds.values_list('embed_type', flat=True).distinct())
        third_party_dict['address_leak_view'] = embeds_onview.filter(leaks_address=True).exists()
        third_party_dict['address_leak_click'] = embeds_onclick.filter(leaks_address=True).exists()
        third_party_dict['sets_cookie'] = embeds.filter(sets_cookie=True).exists()
        third_party_dict['receives_identifier'] = embeds.filter(receives_identifier=True).exists()
        third_parties_dict[third_party] = third_party_dict
    # static_links =
    # num_pairs, ratio, minimum, maximum, mean, median = analyze_differences_between_similar_mails(service)
    # Generate site params
    site_params = {
        # old params
        # 'idents': idents,
        # 'unconfirmed_idents': unconfirmed_idents,
        # 'resources': resources,
        # 'links': links,
        'count_mails': count_mails,
        'count_mult_ident_mails': count_mult_ident_mails,
        # 'connections': connections,
        # 'tracker': tracker,

        # new params
        # 'service': The service itself
        # 'idents': Queryset of identities of the service
        # 'count_mails': Number of emails received by the service
        # 'unconfirmed_idents': Queryset of unconfiremd identities
        # 'sets_cookies':  Bool: Uses cookies in any way (view and click).
        # 'leaks_address': Bool: Discloses email address in any way (view and click).
        'leak_algorithms': algos,
        'cookies_set_avg': cookies_set_mean,  # done
        # 'num_different_thirdparties': Number of different third parties
        # List different third parties, how embedded, address leak : done
        'third_parties': third_parties_dict,  # done
        # third_parties_dict = {
            # third_party: {
            #     'embed_as': list(embedtypes)
            #     'address_leak_view': Bool
            #     'address_leak_click': Bool
            #     'sets_cookie': Bool
            #     'receives_identifier': Bool }
        # Leaks email address to third party in any way : done
        'percent_links_personalised': ratio * 100,  # done
        'avg_personalised_anchor_links': avg_personalised_anchor_links,
        'avg_personalised_image_links': avg_personalised_image_links,
        'num_embedded_links': avg_num_embedded_links,
        # 'personalised_url': 'example.url',  # URL of with (longest) identifier
        # compare DOM-Tree of similar mails
        'suspected_AB_testing': emails.filter(possible_AB_testing=True).exists(),
        'third_party_spam': third_party_spam,  # Marked as receiving third party spam.
        'cache_dirty': False,
        'cache_timestamp': datetime.now().time(),
        # Information about the service itself is added by the wrapper loading the cache.
        # The service object will be available as site_params["service"].
    }
    # print ('AVG_ANCHOR: {}, AVG_IMAGE: {}, RATIO: {}, AVG_LINKS: {}'.format(avg_personalised_anchor_links, avg_personalised_image_links, ratio * 100, avg_num_embedded_links))
    # Cache the result
    cache.set(service.derive_service_cache_path(), site_params)


def analyse_dirty_services():
    # Re-generate caches for services with updated data
    # TODO Can this be parallelized
    dirty_services = Service.objects.filter(resultsdirty=True)
    for dirty_service in dirty_services:
        dirty_service.set_has_approved_identity()
        print(dirty_service)
        analyze_differences_between_similar_mails(dirty_service)
        print('Differences Done')
        for mail in dirty_service.mails():
            mail.analyze_mail_connections_for_leakage()
            mail.create_service_third_party_connections()
        dirty_service.resultsdirty = False
        dirty_service.save()
        create_service_cache(dirty_service, True)


class Analyser(CronJobBase):
    RUN_EVERY_MINS = 2 * 60  # every 2 hours

    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'org.privacy-mail.analyser'    # a unique code

    # ser = Service.objects.get(pk=1)
    # tp = Thirdparty.objects.get(pk=1)
    # embedding = ServiceThirdPartyEmbeds.objects.create(
    #     service=ser, thirdparty=tp)

    def notify_webhook(self, case):
        if settings.CRON_WEBHOOKS:
            try:
                url = settings.CRON_WEBHOOKS['mailfetcher.analyser_cron.Analyser'][case]
                if url:
                    requests.get(url)
            except Exception:
                logger.warning("Analyser.notify_webhook: Failed to send signal.", exc_info=True)
                # No matter what happens here
                pass

    def do(self):

        try:
            self.notify_webhook('start')
            analyse_dirty_services()

            # get_stats_of_mail(Mail.objects.get(id=1899))
            # address_leakage_statistics()

            self.notify_webhook('success')
        except Exception as e:
            logger.error("AnalyserCron: Exception encoutered: %s" % e.__class__.__name__, exc_info=True)
            traceback.print_exc()
            self.notify_webhook('fail')


# returns the number of third party resources in the set and a list of the third parties involved.
def third_parties_in_eresource_set(mail, eresource_set):
    third_party_embeds = 0  # total embeds
    # What kind of third parties
    third_parties = {}
    # identities of mail
    id_of_mail = mail.identity.all()
    if id_of_mail.count() > 0:
        # all resources, that are pulled when viewing mail that don't contain the domain of the
        # service in their url
        service_ext = tldextract.extract(id_of_mail[0].service.url)
        # eresource_set = eresource_set.exclude(url__contains=ext.domain)
        # also not our local host
        # eresource_set = eresource_set.exclude(url__contains=settings.LOCALHOST_URL)
        # third_party_embeds = eresource_set.count()

        for eresource in eresource_set:
            resource_ext = tldextract.extract(eresource.url)
            if service_ext.domain in resource_ext.domain or \
                    tldextract.extract(settings.LOCALHOST_URL).registered_domain in (resource_ext.domain + '.' + resource_ext.suffix):
                continue
            third_party_domain = resource_ext.domain + '.' + resource_ext.suffix
            third_party_embeds += 1
            if third_party_domain in third_parties:
                third_parties[third_party_domain] += 1
            else:
                third_parties[third_party_domain] = 1
    third_parties_list = []
    for third_party in third_parties.keys():
        third_parties_list.append(third_party)
    return third_party_embeds, third_parties_list


def is_third_party(identity, eresource):
    service_ext = tldextract.extract(identity.service.url)
    resource_ext = tldextract.extract(eresource.url)
    if service_ext.domain in resource_ext.domain or \
            tldextract.extract(settings.LOCALHOST_URL).registered_domain in (resource_ext.domain + '.' + resource_ext.suffix):
        return False
    else:
        return True


# analyze one mail in more detail.
def get_stats_of_mail(mail):
    num_third_parties_view = 0
    num_third_parties_static = 0
    print('Analyzing mail of service: {}'.format(mail.identity.all()[0].service))
    eresources_on_view = Eresource.objects.filter(mail=mail).filter(type='con')
    print('{} eresources loaded when viewing mail.'.format(eresources_on_view.count()))

    eresources_static = eresources_on_view.filter(is_start_of_chain=True)
    directly_embedded_third_party_count, directly_embedded_parties = \
        third_parties_in_eresource_set(mail, eresources_static)
    print('{} links directly embedded ({} of them third party) in mail.'.
          format(eresources_static.count(), directly_embedded_third_party_count))
    print('Third parties: {}'.format(directly_embedded_parties))

    additionaly_loaded_eresource_set = eresources_on_view.filter(is_start_of_chain=False)
    additionaly_loaded__third_party_count, additionaly_loaded_parties = \
        third_parties_in_eresource_set(mail, additionaly_loaded_eresource_set)
    print('{} additional ones loaded through forwards ({} of them third party)'.
          format(additionaly_loaded_eresource_set.count(), additionaly_loaded__third_party_count))
    print('Third parties: {}'.format(additionaly_loaded_parties))
    print('')

    leak_eresource_set = Eresource.objects.filter(mail=mail).filter(possible_unsub_link=False). \
        exclude(mail_leakage__isnull=True)
    leak_eresource_set_count = leak_eresource_set.count()

    num_of_leaks_to_third_parties = 0
    num_of_leaks_through_forwards = 0
    ids_of_mail = mail.identity.all()
    chains = []
    leaking_methods = []
    if ids_of_mail.count() > 0:
        for r in leak_eresource_set:
            if is_third_party(ids_of_mail[0], r):
                num_of_leaks_to_third_parties += 1
            if not r.is_start_of_chain:
                num_of_leaks_through_forwards += 1
                chains.append(get_url_chain(r))
                leaking_methods.append(r.mail_leakage)
    print('{} of included urls/websites (including first party, nondistinct) receive eMail address as'
          ' hash, {} of them third party url and {} through forwards.'.
          format(leak_eresource_set_count, num_of_leaks_to_third_parties,
                 num_of_leaks_through_forwards))
    print('The url chains, leaking the address via {}'.format(leaking_methods))
    for chain in chains:
        for r in chain:
            print(r.url)
        print('')

    link_clicked_eresource_set = Eresource.objects.filter(mail=mail).filter(type='con_click')
    longest_chain_len = 0
    longest_chain = []
    if ids_of_mail.count() > 0:
        for r in link_clicked_eresource_set:
            if not is_third_party(ids_of_mail[0], r):
                continue
            chain = get_url_chain(r)
            if len(chain) > longest_chain_len:
                longest_chain_len = len(chain)
                longest_chain = chain
        print('{} urls are in the longest redirect chain that can be triggered by clicking a link'
              .format(longest_chain_len))
        for r in longest_chain:
            print(r.url)
    print('End of mail analyzation')



def analyze_differences_between_similar_mails(service):
    """
    Compares similar mails of a service.
    :param service: Which service to analyse.
    :return: num_pairs, ratio (personalised-/all links), minimum, maximum, mean, median
    """
    # counter = 0
    already_processed_mails = {}
    # mail_set = Mail.objects.all()
    mail_set = service.mails()
    # service_mail_metrics = {}
    pairs_analysed = 0
    diff_links_list = []
    total_num_links_list = []
    min_diff_list = []
    max_diff_list = []
    mean_diff_list = []
    median_diff_list = []
    ratio_list = []
    for m in mail_set:
        # TODO look for pairs instead of single mails, that have already been processed
        if m.id in already_processed_mails:
            continue

        already_processed_mails[m.id] = True
        identity = m.identity.all()
        if identity.count() > 0:
            identity = identity[0]
        else:
            logger.info('No associated identity with mail.', extra={'MailId': m.id})
            print('No associated identity with mail: {}'.format(m.id))
            continue
        # service = identity.service.name
        # results = {}
        # print(m)
        similar_mails = m.get_similar_mails_of_different_identities()
        if len(similar_mails) == 0:
            continue
        for el in similar_mails:
            # if el.id in already_processed_mails:
            #     continue
            pairs_analysed += 1
            already_processed_mails[el.id] = True
            # print(el)
            difference_measure, differences = m.compare_text_of_mails(el)
            # print(difference_measure)
            # if difference_measure < 0.9993:
            if difference_measure < 0.985:
                # logger.warning('Possible A/B testing', extra={'ID first mail': m.id, 'ID second mail': el.id,
                #                                               'differences': differences})
                m.possible_AB_testing = True
                m.save()
                el.possible_AB_testing = True
                el.save()
                continue
                # print(differences)
            else:
                # print(m.get_similar_links(el))
                # m.get_similar_links(el)
                similar_links, num_diff_links, num_total_links, min_difference, max_difference, mean, median = \
                    m.get_similar_links(el, False)
                # if len(similar_links) == 0:
                #     continue
                try:
                    ratio_list.append(num_diff_links / num_total_links)
                except ZeroDivisionError:
                    ratio_list.append(0)
                diff_links_list.append(num_diff_links)
                total_num_links_list.append(num_total_links)
                min_diff_list.append(min_difference)
                max_diff_list.append(max_difference)
                mean_diff_list.append(mean)
                median_diff_list.append(median)
    if pairs_analysed == 0:
        return 0, -1, -1, -1, -1, -1
    try:
        ratio = statistics.mean(ratio_list)
        minimum = statistics.mean(min_diff_list)
        maximum = statistics.mean(max_diff_list)
        mean = statistics.mean(mean_diff_list)
        median = statistics.mean(median_diff_list)
        return pairs_analysed, ratio, minimum, maximum, mean, median
    except (statistics.StatisticsError, UnboundLocalError):
        return -1, -1, -1, -1, -1, -1


def thesis_link_personalisation_of_services():
    # services = Service.objects.filter(hasApprovedIdentity=True)
    services = services_receiving_mails()
    service_mail_metrics = {}

    print('Results of comparing links between similar mails of a service (per mail pair mean).')
    print('#pairs = number of total pairs compared')
    print('ratio =mean(number of different links/total number of links)')
    print('min = the mean minimum of different chars per different link')
    print('max = the mean maximum of different chars per different link')
    print('mean = the mean number of different chars per different link')
    print('median = the mean median of different chars per different link')
    print('{:<25}: {:<6} : {:<7}: {:<7}: {:<7}: {:<7}'.format('Service', '#pairs', 'min',
                                                                    'max', 'mean', 'median'))
    ratios = []
    minimums = []
    maximums = []
    medians = []
    means = []
    num_services_without_pairs = 0
    services_without_pairs = []

    for service in services:
        service_name = service.name
        # if 'pearl' not in service.name:
        #     continue
        num_pairs, ratio, minimum, maximum, mean, median = analyze_differences_between_similar_mails(service)
        service_mail_metrics[service] = {}
        service_mail_metrics[service]['ratio'] = ratio
        service_mail_metrics[service]['minimum'] = minimum
        minimums.append(minimum)
        service_mail_metrics[service]['maximum'] = maximum
        maximums.append(maximum)
        service_mail_metrics[service]['median'] = median
        medians.append(median)
        service_mail_metrics[service]['mean'] = mean
        means.append(mean)
        if num_pairs == 0:
            num_services_without_pairs += 1
            services_without_pairs.append(service_name)
            continue
        print('{:<25}: {:<6} : {:<7.2f}: {:<7.2f}: {:<7.2f}: {:<7.2f}'
              .format(service_name, num_pairs, minimum, maximum, mean, median))
    mean_minimum = statistics.mean(minimums)
    mean_maximum = statistics.mean(maximums)
    mean_median = statistics.mean(medians)
    mean_mean = statistics.mean(means)
    print('{:<25}: {:<6} : {:<7.2f}: {:<7.2f}: {:<7.2f}: {:<7.2f}'.format('Total Mean', '', mean_minimum, mean_maximum,
                                                                          mean_mean, mean_median))
    print('Services without pairs: {}'.format(num_services_without_pairs))
    print(services_without_pairs)

    print('\n\n')
        # counter = 0
        # personalised_links = []
        # total_links = []
        # for mail in service.mails():
        #     counter += 1
        #     all_static_eresources = Eresource.objects.filter(mail=mail).\
        #         filter(Q(type='a') | Q(type='link') | Q(type='img') | Q(type='script'))
        #     total_links.append(all_static_eresources.count())
        #     personalised_mails = all_static_eresources.filter(personalised=True)
        #     personalised_links.append(personalised_mails.count())
        # if counter == 0:
        #     # print('Continue')
        #     continue
        # ratio = statistics.mean(personalised_links) / statistics.mean(total_links)



def thesis_link_personalisation_of_services_only_eresources(services_to_skip=''):
    # Compute summaries for personalisation of statically extracted URLs.
    services = Service.objects.all()
    print('Results of comparing links between similar mails of a service (per mail mean).')
    print('Ratio Total = Ratio of all embedded URLs in the HTML Body that are personalised')
    print('Ratio Images = Ratio of embedded image URLs in the HTML Body that are personalised')
    print('Ratio Links = Ratio of embedded link (anchor tags) URLs in the HTML Body that are personalised')
    print('Ratio Other = Ratio of other (script and link tags) embedded URLs in the HTML Body that are personalised')
    print('{:<25}: {:<12}: {:<12}: {:<12}: {:<12}: {:<12}: {:<12}: {:<12}: {:<12}: {:<12}: {:<12}: {:<12}: {:<12}'
          .format('Service', 'Pers mean', 'Mean Total', 'Ratio Total', 'pers images', 'Mean Images', 'Ratio Images',
                   'pers links', 'Mean Links', 'Ratio Links', 'pers other',
                  'Mean Other', 'Ratio Other'))
    for service in services:
        service_name = service.name
        if service_name in services_to_skip:
            continue

        counter = 0
        personalised_links = []
        personalised_anchor_urls = []
        personalised_img_urls = []
        personalised_other_urls = []
        total_anchor_urls = []
        total_img_urls = []
        total_other_urls = []
        total_urls = []
        for mail in service.mails():
            counter += 1
            all_static_eresources = Eresource.objects.filter(mail=mail).\
                filter(Q(type='a') | Q(type='link') | Q(type='img') | Q(type='script'))
            personalised_anchor_urls_eresources = all_static_eresources.filter(type='a')
            personalised_img_urls_eresources = all_static_eresources.filter(type='img')
            personalised_other_eresources = all_static_eresources.exclude(type='a').exclude(type='img')

            total_urls.append(all_static_eresources.count())
            total_anchor_urls.append(personalised_anchor_urls_eresources.count())
            total_img_urls.append(personalised_img_urls_eresources.count())
            total_other_urls.append(personalised_other_eresources.count())

            personalised_anchor_urls.append(personalised_anchor_urls_eresources.filter(personalised=True).count())
            personalised_img_urls.append(personalised_img_urls_eresources.filter(personalised=True).count())
            personalised_other_urls.append(personalised_other_eresources.filter(personalised=True).count())
            personalised_links.append(all_static_eresources.filter(personalised=True).count())
        if counter == 0:
            # print('Continue')
            continue

        mean_personalised_total = statistics.mean(personalised_links)
        mean_personalised_img_urls = statistics.mean(personalised_img_urls)
        mean_personalised_anchor_urls = statistics.mean(personalised_anchor_urls)
        mean_personalised_other_urls = statistics.mean(personalised_other_urls)

        mean_total = statistics.mean(total_urls)
        if mean_total > 0:
            ratio_total = statistics.mean(personalised_links) / mean_total
        else:
            ratio_total = 0
        mean_images = statistics.mean(total_img_urls)
        if mean_images > 0:
            ratio_personalised_images = statistics.mean(personalised_img_urls) / mean_images
        else:
            ratio_personalised_images = 0
        mean_anchors = statistics.mean(total_anchor_urls)
        if mean_anchors > 0:
            ratio_personalised_anchors = statistics.mean(personalised_anchor_urls) / mean_anchors
        else:
            ratio_personalised_anchors = 0
        mean_other_urls = statistics.mean(total_other_urls)
        if mean_other_urls > 0:
            ratio_other_urls = statistics.mean(personalised_other_urls) / mean_other_urls
        else:
            ratio_other_urls = 0
        # if service_name == 'spd.de':
        #     print('')
        print('{:<25}: {:<12.2f}: {:<12.2f}: {:<12.2f}: {:<12.2f}: {:<12.2f}: {:<12.2f}: {:<12.2f}: {:<12.2f}:'
              ' {:<12.2f}: {:<12.2f}: {:<12.2f}: {:<12.2f}'
              .format(service_name, mean_personalised_total, mean_total, ratio_total, mean_personalised_img_urls,
                      mean_images, ratio_personalised_images, mean_personalised_anchor_urls, mean_anchors
                      , ratio_personalised_anchors, mean_personalised_other_urls, mean_other_urls, ratio_other_urls))
    print('\n\n')

def chains_calculation_helper(eresource_set, show_statistics=False, print_long_chains=False, chains_lengths_to_print=5,
                              analyse_syncs=False):
    # This function is very inefficient and memory intensive! Think of a better way to get the median and rewrite this!
    leak_chains = {}
    service_dict = {}
    for e in eresource_set:  # \
        # .exclude(url__icontains='examiner').exclude(url__icontains='nbcnews'):
        resource_chain = get_url_chain(e)
        chain = []
        for u in resource_chain:
            chain.append(u.url)

        if len(chain) <= 1:
            continue
        # if len_chain > 5:
        # longest_chain = len_chain
    #     leak_chains.set(chain)
    # for chain in leak_chains:
        r = resource_chain[0]
        identity = r.mail.identity.all()
        if identity.count() > 0:
            service_name = r.mail.identity.get().service
            if service_name in service_dict:
                if len(chain) > len(service_dict[service_name]['longest_chain']):
                    service_dict[service_name]['longest_chain'] = chain
                    service_dict[service_name]['chain_lengths'].append(len(chain))
                else:
                    service_dict[service_name]['chain_lengths'].append(len(chain))
            else:
                service_dict[service_name] = {
                    'longest_chain': chain,
                    'chain_lengths': [len(chain)],
                    'sync_chains': [],
                    'syncing': False
                }

            # check if we visit a domain a second time, after visiting other domains.
            if analyse_syncs:
                prev_domains = set()

                domain_chain = []
                last_domain = ''
                for url in chain:
                    domain_chain.append(tldextract.extract(url).registered_domain)
                for counter, domain in enumerate(domain_chain):
                    if counter == 1:
                        prev_domains.add(domain)
                        last_domain = domain
                        continue
                    if domain == last_domain:
                        continue
                    if domain != last_domain:
                        if domain in prev_domains:
                            # service_dict[service_name]['sync_chains'].append(chain)
                            service_dict[service_name]['syncing'] = True
                            continue
                        else:
                            prev_domains.add(domain)

    if show_statistics:
        # print('Service = Number of mails that try load the third party')
        total_means = 0
        total_medians = 0
        total_max = 0
        total_num_chains_per_mail = 0
        service_count = 1
        print('mean = Mean length of redirection chains')
        print('median = Median length of redirection chains')
        print('max = Maximum length of redirection chains')
        print('num_found_chains = Number of chains per mail')
        print('{:<25} : {:<6}: {:<6}: {:<6}: {:<11}: {:<6}'.format('####### Service', 'mean', 'median', 'max',
                                                                   'chains/mail', ' Syncing ######'))
        for service in service_dict.keys():
            mean_length = statistics.mean(service_dict[service]['chain_lengths'])
            total_means += mean_length
            median_length = statistics.median(service_dict[service]['chain_lengths'])
            total_medians += median_length
            max_length = max(service_dict[service]['chain_lengths'])
            total_max += max_length
            num_chains_per_mail = len(service_dict[service]['chain_lengths'])/service.mails().count()
            total_num_chains_per_mail += num_chains_per_mail
            service_count += 1
            print('{:<25} : {:<6.2f}: {:<6.2f}: {:<6.2f}: {:<11.2f}: {:<6}'.format(
                service.name, mean_length, median_length, max_length, num_chains_per_mail,
                service_dict[service]['syncing']))
        print('\n')
        print('{:<25} : {:<6.2f}: {:<6.2f}: {:<6.2f}: {:<6.2f}'.format('All Services Mean', total_means / service_count,
                                                                       total_medians / service_count,
                                                                       total_max / service_count,
                                                                       total_num_chains_per_mail / service_count))
        # if analyse_syncs:
        #     print('Printing syncchains of each service:')
        #     for service in service_dict.keys():
        #         print(service)
        #         for url in service_dict[service]['sync_chains']:
        #             print(url)
        #         print('\n')
        #     print(LONG_SEPERATOR)
        #     print('\n')

    if print_long_chains:
        print('Printing longest chains of each service:')
        for service in service_dict.keys():
            if len(service_dict[service]['longest_chain']) >= chains_lengths_to_print:
                print(service)
                for url in service_dict[service]['longest_chain']:
                    print(url)
                print('\n')


def long_chains_calculation():
    print(LONG_SEPERATOR)
    print('############# The longest chains that leaks the mailaddress when viewing: #############')
    # longest_chain = 0
    eresource_set = Eresource.objects.filter(type='con').exclude(possible_unsub_link=True) \
            .exclude(is_start_of_chain=False).exclude(is_end_of_chain=True).exclude(mail_leakage__isnull=True)
            # .filter(url__contains='washingtonexaminer')
    chains_calculation_helper(eresource_set, True, True, analyse_syncs=True)

    print(LONG_SEPERATOR)
    print('############# The longest chains that leaks the mailaddress when clicking: #############')
    # longest_chain = 0
    eresource_set = Eresource.objects.filter(type='con_click').exclude(possible_unsub_link=True) \
        .exclude(is_start_of_chain=False).exclude(is_end_of_chain=True).exclude(mail_leakage__isnull=True)
    # .filter(url__contains='washingtonexaminer')
    chains_calculation_helper(eresource_set, True, True, analyse_syncs=True)

    print(LONG_SEPERATOR)
    print('############# The longest chains for an embedded (viewing) external resource: #############')
    eresource_set = Eresource.objects.filter(type='con').exclude(possible_unsub_link=True) \
            .exclude(is_start_of_chain=False).exclude(is_end_of_chain=True)
    # .filter(url__contains='washingtonexaminer')
    chains_calculation_helper(eresource_set, True, True, analyse_syncs=True)

    print(LONG_SEPERATOR)
    print('############# The longest chain after clicking a link: #############')
    eresource_set = Eresource.objects.filter(type='con_click').exclude(is_start_of_chain=False)\
        .exclude(is_end_of_chain=True)
    chains_calculation_helper(eresource_set, True, True, analyse_syncs=True)


def get_url_chain(eresource):
    url_chain = []
    url_chain.append(eresource)

    # search for eresources in chain before given eresource
    start_of_chain_reached = eresource.is_start_of_chain
    while not start_of_chain_reached:
        e = Eresource.objects.filter(redirects_to_channel_id=url_chain[0].channel_id)[0]
        start_of_chain_reached = e.is_start_of_chain
        url_chain.insert(0, e)
    end_of_chain_reached = eresource.is_end_of_chain
    while not end_of_chain_reached:
        try:
            e = Eresource.objects.filter(channel_id=url_chain[-1].redirects_to_channel_id)[0]
            end_of_chain_reached = e.is_end_of_chain
            url_chain.append(e)
        # Should happen if the end of the chain has not been added, as it was a third party when clicking
        except:
            end_of_chain_reached = True
    return url_chain


# def third_party_analization_general_new():

def analyse_contacted_domains_from_cache():
    contacted_domains = {}
    services_queryset = services_receiving_mails()

    services_that_open_connections_click = 0
    services_that_open_connections_view = 0
    services_that_open_connections_combined = 0
    for service in services_queryset:
        contacted_domains_set_click = ServiceThirdPartyEmbeds.objects.filter(embed_type='ONCLICK').filter(service=service)
        contacted_domains_set_view = ServiceThirdPartyEmbeds.objects.filter(embed_type='ONVIEW').filter(service=service)
        contacted_domains_set_combined = ServiceThirdPartyEmbeds.objects.filter(Q(embed_type='ONCLICK') |
                                                                                Q(embed_type='ONVIEW')).filter(service=service)
        if contacted_domains_set_click.exists():
            services_that_open_connections_click += 1
        if contacted_domains_set_view.exists():
            services_that_open_connections_view += 1
        if contacted_domains_set_combined.exists():
            services_that_open_connections_combined += 1

    ratio_on_view = services_that_open_connections_view / num_services_receiving_mails() * 100
    ratio_on_click = services_that_open_connections_click / num_services_receiving_mails() * 100
    ratio_on_combined = services_that_open_connections_combined / num_services_receiving_mails() * 100

    print('Services that open Connections:')
    print('{:<10} : {:<17}: {:<5}'.format('Scenario','number of services', '%'))

    print('{:<10} : {:<17} : {:<5.2f}'.format('VIEW', services_that_open_connections_view , ratio_on_view))
    print('{:<10} : {:<17} : {:<5.2f}'.format('CLICK', services_that_open_connections_click , ratio_on_click))
    print('{:<10} : {:<17} : {:<5.2f}'.format('COMBINED', services_that_open_connections_combined , ratio_on_combined))

    # print('OnView: {:5<2f}%, OnClick: {:<2f}%, Combined: {:<2f}%'.format(ratio_on_click, ratio_on_view, ratio_on_combined))




    #     service_cache = cache.get(service.derive_thirdparty_cache_path())
    #     if service_cache is None:
    #         create_service_cache(service, force=False)
    #         service_cache = cache.get(service.derive_thirdparty_cache_path())
    #     services = service_cache['services']
    #     services_list = []
    #     for i in list(services.keys()):
    #         services_list.append(i.name)
    #     contacted_domains[service_cache] = services_list
    #
    # for contacted_domain in sorted(contacted_domains, key=lambda k: len(contacted_domains[k]), reverse=True):
    #     print(
    #         '{:<30} : {:<4} : {:<4}'.format(contacted_domain.name, len(contacted_domains[contacted_domain])
    #                                         , str(contacted_domains[contacted_domain])))
    # for contacted_domain in contacted_third_party_domains:
    #     print('{:<16} : {:<4} : {:<4}'.format(contacted_domain.name, len(contacted_third_party_domains[contacted_domain])
    #           , str(contacted_third_party_domains[contacted_domain])))


    #
    # for service in third_party_by_service:
    #     num_third_party_by_service[service] = len(third_party_by_service[service])
    # s = [(k, num_third_party_by_service[k]) for k in sorted(num_third_party_by_service,
    #                                                         key=num_third_party_by_service.get,
    #                                                         reverse=True)]
    #
    # for k, v in s:
    #     print('{:<25}: {:<5}: {}'.format(k, v, str(third_party_by_service[k])))
    # print('\n\n')


def third_party_analization_general():
    # This function is a mess and needs refactoring badly. :/

    service_by_third_party = {}  # third_party : number of services
    third_party_by_service = {}  # service : third parties

    for service in services_receiving_mails():
        third_parties_this_mail = {}
        for mail in service.mails().exclude(processing_fails=3):
            # check if we already have this service in our dict
            if service.name not in third_party_by_service:
                third_party_by_service[service.name] = set()

            service_ext = tldextract.extract(service.url)
            eresource_set = mail.eresource_set.filter(type='con')
            # also not our local host
            for eresource in eresource_set:
                resource_ext = tldextract.extract(eresource.url)
                third_party_domain = resource_ext.domain + '.' + resource_ext.suffix
                if service_ext.domain in resource_ext.domain or \
                        tldextract.extract(settings.LOCALHOST_URL).registered_domain in third_party_domain:
                    continue
                third_party_by_service[service.name].add(third_party_domain)
                if third_party_domain in third_parties_this_mail:
                    third_parties_this_mail[third_party_domain] += 1
                else:
                    third_parties_this_mail[third_party_domain] = 1

            eresource_set = mail.eresource_set.filter(type='con')
            # also not our local host
            for eresource in eresource_set:
                resource_ext = tldextract.extract(eresource.url)
                third_party_domain = resource_ext.domain + '.' + resource_ext.suffix
                if service_ext.domain in resource_ext.domain or \
                        tldextract.extract(settings.LOCALHOST_URL).registered_domain in third_party_domain:
                    continue
                if third_party_domain in third_parties_this_mail:
                    third_parties_this_mail[third_party_domain] += 1
                else:
                    third_parties_this_mail[third_party_domain] = 1

        for third_party_domain in third_parties_this_mail.keys():
            if third_party_domain in service_by_third_party:

                # service_by_third_party[third_party_domain] += 1
                service_by_third_party[third_party_domain].add(service.name)
            else:
                service_by_third_party[third_party_domain] = set()
                service_by_third_party[third_party_domain].add(service.name)

    print(LONG_SEPERATOR + '\n')
    print('Services that embed third parties without clicking links:')
    # Count, how many third parties each service uses.
    num_third_party_by_service = {}
    for service in third_party_by_service:
        num_third_party_by_service[service] = len(third_party_by_service[service])
    s = [(k, num_third_party_by_service[k]) for k in sorted(num_third_party_by_service,
                                                            key=num_third_party_by_service.get,
                                                            reverse=True)]

    for k, v in s:
        if len(third_party_by_service[k]) == 0:
            third_party_by_service[k] = {}
        print('{:<25}: {:<5}: {}'.format(k, v, str(third_party_by_service[k])))
    print('\n\n')

    third_party_by_service_clicked = {}  # service : third parties
    for service in services_receiving_mails():
        for mail in service.mails().exclude(processing_fails=3):
            # check if we already have this service in our dict
            if service.name not in third_party_by_service_clicked:
                third_party_by_service_clicked[service.name] = set()
            service_ext = tldextract.extract(service.url)
            eresource_set = mail.eresource_set.filter(type='con_click')
            # also not our local host
            for eresource in eresource_set:
                resource_ext = tldextract.extract(eresource.url)
                third_party_domain = resource_ext.domain + '.' + resource_ext.suffix
                if service_ext.domain in resource_ext.domain or \
                        tldextract.extract(settings.LOCALHOST_URL).registered_domain in third_party_domain:
                    continue
                third_party_by_service_clicked[service.name].add(third_party_domain)
    print(LONG_SEPERATOR)
    print('Services that embed third parties when only clicking links:')
    # Count, how many third parties each service uses.
    num_third_party_by_service_clicked = {}
    for service in third_party_by_service:
        num_third_party_by_service_clicked[service] = len(third_party_by_service_clicked[service])
    s = [(k, num_third_party_by_service_clicked[k])
         for k in sorted(num_third_party_by_service_clicked, key=num_third_party_by_service_clicked.get,
                         reverse=True)]
    for k, v in s:
        if len(third_party_by_service_clicked[k]) == 0:
            third_party_by_service_clicked[k] = {}
        print('{:<25}: {:<5}: {}'.format(k, v, str(third_party_by_service_clicked[k])))
    print('\n\n')

    # Clicked and viewed combined
    third_party_by_service_clicked = {}  # service : third parties
    for service in services_receiving_mails():
        for mail in service.mails().exclude(processing_fails=3):
            # check if we already have this service in our dict
            if service.name not in third_party_by_service_clicked:
                third_party_by_service_clicked[service.name] = set()
            service_ext = tldextract.extract(service.url)
            eresource_set = mail.eresource_set.filter(type__contains='con')
            # also not our local host
            for eresource in eresource_set:
                resource_ext = tldextract.extract(eresource.url)
                third_party_domain = resource_ext.domain + '.' + resource_ext.suffix
                if service_ext.domain in resource_ext.domain or \
                        tldextract.extract(settings.LOCALHOST_URL).registered_domain in third_party_domain:
                    continue
                third_party_by_service_clicked[service.name].add(third_party_domain)
    print(LONG_SEPERATOR)
    print('Services that embed third parties combined:')
    # Count, how many third parties each service uses.
    num_third_party_by_service_clicked = {}
    for service in third_party_by_service:
        num_third_party_by_service_clicked[service] = len(third_party_by_service_clicked[service])
    s = [(k, num_third_party_by_service_clicked[k])
         for k in sorted(num_third_party_by_service_clicked, key=num_third_party_by_service_clicked.get,
                         reverse=True)]
    for k, v in s:
        if len(third_party_by_service_clicked[k]) == 0:
            third_party_by_service_clicked[k] = {}
        print('{:<25}: {:<5}: {}'.format(k, v, str(third_party_by_service_clicked[k])))
    print('\n\n')



    # How many % of mails embed third party resources?
    all_mails = Mail.objects.all().exclude(processing_fails=3)
    third_party_embeds = 0  # total embeds
    list_third_party_per_mail = []  # number of third parties per mail
    high = 0  # highest number of embeds per mail
    low = 50000  # lowest number of embeds per mail
    service_set_embedding_resources = set()
    # What kind of third parties
    third_party_count_per_mail = []
    third_parties = {}
    third_parties_min = 5000
    third_parties_max = 0
    services_per_thirdparty = {}
    for mail in all_mails:
        third_parties_this_mail = {}
        # identities of mail
        id_of_mail = mail.identity.all()
        if id_of_mail.count() > 0:
            # all resources, that are pulled when viewing mail that don't contain the domain of the
            # service in their url
            service_ext = tldextract.extract(id_of_mail[0].service.url)
            eresource_set = mail.eresource_set.filter(type__contains='con')
            new_eresource_set = []
            # also not our local host
            for eresource in eresource_set:
                resource_ext = tldextract.extract(eresource.url)
                third_party_domain = resource_ext.domain + '.' + resource_ext.suffix
                if tldextract.extract(settings.LOCALHOST_URL).registered_domain in third_party_domain or \
                        service_ext.domain in resource_ext.domain:

                    continue
                new_eresource_set.append(eresource)
                service_set_embedding_resources.add(id_of_mail[0].service)

                if third_party_domain in third_parties_this_mail:
                    third_parties_this_mail[third_party_domain] += 1
                else:
                    third_parties_this_mail[third_party_domain] = 1
            for third_party_domain in third_parties_this_mail.keys():
                if third_party_domain in third_parties:
                    third_parties[third_party_domain] += 1
                else:
                    third_parties[third_party_domain] = 1
            i = len(new_eresource_set)
            list_third_party_per_mail.append(i)
            if i > 0:
                third_party_embeds = third_party_embeds + 1
            if i > high:
                high = i
            if i < low:
                low = i
            third_parties_this_mail_count = len(third_parties_this_mail)
            if third_parties_this_mail_count > third_parties_max:
                third_parties_max = third_parties_this_mail_count
            if third_parties_this_mail_count < third_parties_min:
                third_parties_min = third_parties_this_mail_count
            third_party_count_per_mail.append(third_parties_this_mail_count)
    percent_of_mail_embed = len(service_set_embedding_resources) / (Service.objects.all().count()
                                                                    - num_services_without_mails()) * 100
    print(LONG_SEPERATOR)
    print('{:.2f}% of services have third party resources embedded. ({} of total {})'
          .format(percent_of_mail_embed, len(service_set_embedding_resources),
                  Service.objects.all().count() - num_services_without_mails()))

    print('{:.2f} third party resources on average per mail with a median of {}'.format(
        statistics.mean(list_third_party_per_mail), statistics.median(list_third_party_per_mail)))
    print('Min. ext resources of a mail: {}'.format(low))
    print('Max. ext resources of a mail: {}\n'.format(high))

    print(LONG_SEPERATOR)
    print('{} different third parties found.'.format(len(third_parties)))
    print('#mails = Number of mails that try load the third party')
    print('usage = Number of services using the third party')
    print('{:<25} :{:<5}: {}'.format('####### Third Party', 'usage', '#mails ######'))

    num_service_by_third_party = {}
    for third_party in service_by_third_party:
        num_service_by_third_party[third_party] = len(service_by_third_party[third_party])

    s = [(k, num_service_by_third_party[k]) for k in sorted(num_service_by_third_party, key=num_service_by_third_party
                                                            .get, reverse=True)]

    for k, v in s:
        print('{:<25}: {:<5}: {}: {}'.format(k, str(v), str(third_parties[k]), service_by_third_party[k]))

    print(LONG_SEPERATOR)
    print('{:.2f} third parties on average per mail with a median of {}'.format(
        statistics.mean(third_party_count_per_mail), statistics.median(third_party_count_per_mail)))
    print('Min third parties in a mail: {}'.format(third_parties_min))
    print('Max third parties in a mail: {}'.format(third_parties_max))
    print(LONG_SEPERATOR + '\n')


def num_services_without_mails():
    """
    Calculate the number of services that did not receive any emails.
    :return: Number of services that did not receive any emails.
    """
    # Number of services that did not receive any mails.
    num_no_mails_received = 0
    identities_that_receive_mails = set()
    services_without_mails_set = set()
    for service in Service.objects.all():
        identities_that_receive_mails.add(service.name)
        if service.mails().count() == 0:
            identities_that_receive_mails.remove(service.name)
            num_no_mails_received += 1
            services_without_mails_set.add(service)
    # print('Services that did not receive mails: {}'.format(services_without_mails_set))
    # all_mails = Mail.objects.all()
    # print('A total of {} mails have been scanned.'.format(all_mails.count()))
    return num_no_mails_received


def address_leakage_statistics():
    # Get the number of trackers that receive the mailaddress in plain or as hash
    leaking_resources = Eresource.objects.exclude(mail_leakage=None).exclude(possible_unsub_link=True).filter(Q(type="con") | Q(type="con_click"))
    print("Eresources:", leaking_resources.count())
    leaking_services = {}
    trackers = {}
    algos_services = {}
    algos_trackers = {}

    for r in leaking_resources:
        # leaking_mails.append(r.mail)
        leaking_algorithms = r.mail_leakage.split(", ")
        #for id in r.mail.identity.all():
        #    if id.service.name not in leaking_services:
        #        leaking_services[id.service.name] = set()
        #    for algo in leaking_algorithms:
        #        leaking_services[id.service.name].add(algo)

        # record all trackers and how they receive the address
        #if r.host.name not in trackers:
        #    trackers[r.host.name] = set()
        #for algo in leaking_algorithms:
        #    trackers[r.host.name].add(algo)
        for algo in leaking_algorithms:
            if algo not in algos_services:
                algos_services[algo] = set([])
            if algo not in algos_trackers:
                algos_trackers[algo] = set([])
            # Add service
            for id in r.mail.identity.all():
                algos_services[algo].add(id.service.name)
            algos_trackers[algo].add(r.host.name)

    #print('{} different trackers (including the service itself) found,'
    #      ' that receive the mailaddress in plain or as a hash.'
    #      .format(len(trackers)))
    #for tracker in trackers.keys():
    #    print('{:<25} : {}'.format(tracker, trackers[tracker]))
    print("Algos leaked by services:")
    for algo in algos_services.keys():
        print(algo, "\t", len(algos_services[algo]), "\t", algos_services[algo])

    print("Algos leaked to trackers")
    for algo in algos_trackers:
        print(algo, "\t", len(algos_trackers[algo]), "\t", algos_trackers[algo])

    print('')

    # services = {}
    # for i in leaking_identities.keys:
    #     services.append(i.service.name)
    # services = list(set(services))
    num_all_services = Service.objects.all().count() - num_services_without_mails()
    percent_of_services_leaking = round(len(leaking_services) / num_all_services * 100)
    print('{:.2f}% of services have links or connections, that leak the mailaddress in plain or '
          'through a hash. ({} of total {})'
          .format(percent_of_services_leaking, len(leaking_services), num_all_services))
    # print(leaking_services)
    for service in leaking_services.keys():
        print('{:<25} : {}'.format(service, leaking_services[service]))
    print('\n')


def num_services_receiving_mails():
    return Service.objects.all().count() - num_services_without_mails()


def services_receiving_mails():
    services = Service.objects.all()
    valid_services = []
    for service in services:
        if service.mails().exists():
            valid_services.append(service)
    return valid_services


def services_leaking_to_destinations():
    print('Services leaking address to external domains.')
    ser_receiving_mails = services_receiving_mails()
    for service in ser_receiving_mails:
        connections = ServiceThirdPartyEmbeds.objects.filter(service=service).filter(leaks_address=True)
        if not connections.exists():
            continue
        third_parties_tuple_list = list(connections.values_list('thirdparty_id').distinct())
        domains = []
        for tuple in third_parties_tuple_list:
            domains.append(Thirdparty.objects.get(id=tuple[0]).name)

        print('{:<20}: {:<5} : {}'.format(service.name, len(third_parties_tuple_list), domains))


def services_setting_cookies():
    print('Services setting cookies.')
    ser_receiving_mails = services_receiving_mails()
    service_without_cookies = []
    service_without_cookies_view = []
    service_without_cookies_click = []
    third_party_cookies = []
    third_party_cookies_view = []
    third_party_cookies_click = []
    services_with_tp_cookies = 0
    services_with_tp_view = 0
    services_with_tp_click = 0
    for service in ser_receiving_mails:
        connections = ServiceThirdPartyEmbeds.objects.filter(service=service).filter(sets_cookie=True)
        connections_view = connections.filter(embed_type='ONVIEW')
        connections_click = connections.filter(embed_type='ONCLICK')
        third_party_cookies_this_service = []
        third_party_names_all = set()
        third_party_names_view = set()
        third_party_names_click = set()
        for con in connections:
            third_party_names_all.add(con.thirdparty.name)
        for con in connections_view:
            third_party_names_view.add(con.thirdparty.name)
        for con in connections_click:
            third_party_names_click.add(con.thirdparty.name)

        third_party_names_all.discard(service.name)
        third_party_names_all.discard(tldextract.extract(settings.LOCALHOST_URL).registered_domain)

        third_party_names_view.discard(service.name)
        third_party_names_view.discard(tldextract.extract(settings.LOCALHOST_URL).registered_domain)

        third_party_names_click.discard(service.name)
        third_party_names_click.discard(tldextract.extract(settings.LOCALHOST_URL).registered_domain)

        third_party_cookies.append(len(third_party_names_all))
        third_party_cookies_view.append(len(third_party_names_view))
        third_party_cookies_click.append(len(third_party_names_click))

        if len(third_party_names_all) == 0:
            services_with_tp_cookies += 1
        if not connections.exists():
            service_without_cookies.append(service.name)
        if not connections_view.exists():
            service_without_cookies_view.append(service.name)
        if not connections_click.exists():
            service_without_cookies_click.append(service.name)

    print('{:.2f}% of services set any cookies, {} do not.'.format(
        (len(ser_receiving_mails) - len(service_without_cookies))
        / len(ser_receiving_mails) * 100, len(service_without_cookies)))
    print('{:.2f}% of services set cookies on view, {} do not.'.format(
        (len(ser_receiving_mails) - len(service_without_cookies_view))
        / len(ser_receiving_mails) * 100, len(service_without_cookies_view)))
    print('{:.2f}% of services set cookies click, {} do not.'.format(
        (len(ser_receiving_mails) - len(service_without_cookies_click))
        / len(ser_receiving_mails) * 100, len(service_without_cookies_click)))
    print('{:.2f}% of services set third party cookies'.format(services_with_tp_cookies/len(ser_receiving_mails)* 100))
    third_party_cookies.sort()
    print('Number of third party cookies per service:')
    print(third_party_cookies)
    print('Number of third party cookies per service on view:')
    third_party_cookies_view.sort()
    print(third_party_cookies_view)
    print('Number of third party cookies per service on click:')
    third_party_cookies_click.sort()
    print(third_party_cookies_click)



def analyse_ab_testing():
    services_with_ab_testing = set()
    for service in Service.objects.all():
        if service.mails().filter(possible_AB_testing=True).exists():
            services_with_ab_testing.add(service)
    print('Services with suspected A/B testing: {}'.format(services_with_ab_testing))


def general_statistics():
    print(LONG_SEPERATOR)
    all_mails_queryset = Mail.objects.all()
    num_all_mails = all_mails_queryset.count()
    print('Number of mails in Database: {}'.format(num_all_mails))

    failed_mails_qeryset = all_mails_queryset.filter(processing_fails=settings.OPENWPM_RETRIES)
    num_failed_mails = failed_mails_qeryset.count()
    print('Number of failed mails in the Database: {}'. format(num_failed_mails))

    num_failed_mails = failed_mails_qeryset.filter(processing_state='UNPROCESSED').count()
    print('Number of failed mails in the Database while viewing: {}'.format(num_failed_mails))

    num_failed_mails = failed_mails_qeryset.filter(processing_state='VIEWED').count()
    print('Number of failed mails in the Database while clicking a link: {}'.format(num_failed_mails))

    done_mails_qeryset = all_mails_queryset.filter(processing_state='DONE')
    num_done_mails = done_mails_qeryset.count()
    print('Number of done mails in the Database: {}'.format(num_done_mails))

    no_unsubscribe_mails_qeryset = all_mails_queryset.filter(processing_state='NO_UNSUBSCRIBE_LINK')
    num_no_unsubscribe_mails = no_unsubscribe_mails_qeryset.count()
    print('Number of mails without unsub link found in the Database: {}'.format(num_no_unsubscribe_mails))


    all_services_queryset = Service.objects.all()
    num_all_services = all_services_queryset.count()
    print('Number of all services: {}'.format(num_all_services))
    print('Number of services receiving Mails: {}'.format(len(services_receiving_mails())))
    print('Number of services not receiving any mails: {}'.format(num_services_without_mails()))
    print('Number of registered Identities: {}'.format(Identity.objects.all().count()))
    number_of_identities_per_service_list = []
    for service in services_receiving_mails():
        number_of_identities_per_service_list.append(service.identity_set.count())
    print('Average number of identities per Service: {}'.format(statistics.mean(number_of_identities_per_service_list)))
    num_identities_receiving_mails = 0
    for identity in Identity.objects.all():
        if identity.message.count() != 0:
            num_identities_receiving_mails += 1
    print('Number of identities that do receive mails: {}'.format(num_identities_receiving_mails))


    # embedded_type_statistics()


def embedded_type_statistics():
    print(LONG_SEPERATOR)
    print('Statistics embedded URLs in emails.')

    def analyse_one_type(type):
        number_of_embeds = []
        for mail in Mail.objects.all():
            # if 'a' not in type and 'img' not in type:
            #     eresource_set = mail.eresource_set.filter(Q(type='script') | Q(type='link'))
            # else:
            eresource_set = mail.eresource_set.filter(type=type)
            number_of_embeds.append(eresource_set.count())
        mean_embeds = statistics.mean(number_of_embeds)
        median_embeds = statistics.median(number_of_embeds)
        max_embeds = max(number_of_embeds)
        min_embeds = min(number_of_embeds)
        num_without_embeds = number_of_embeds.count(0)
        num_all_mails = Mail.objects.all().count()
        num_with_embeds = num_all_mails - num_without_embeds

        type_description = '<' + type + '>'

        print('{:<20}: {:<7.2f}: {:<7.2f}: {:<7}: {:<14}: {:<14}: {:<.2f}%'.format(type_description, max_embeds,
                                                                      mean_embeds, median_embeds, num_with_embeds, num_without_embeds, num_with_embeds/num_all_mails *100))

    print('{:<20}: {:<7}: {:<7}: {:<7}: {:<14}: {:<14}: {:<14}'.format('Embedded Type', 'max', 'mean',
                                                                              'median', 'mails with', 'mails without',
                                                                              'emails embedding this type'))
    analyse_one_type('a')
    analyse_one_type('img')
    analyse_one_type('link')
    analyse_one_type('script')


def any_connection_overview():
    # Count for each scenario how many emails open open a connection
    mails = Mail.objects.filter(processing_state='DONE')
    print('{} Mails'.format(mails.count()))
    mails_with_view_connections = 0
    mails_with_click_connections = 0
    mails_with_any_connections = 0
    for mail in mails:
        if mail.eresource_set.all().filter(type='con').exists():
            mails_with_view_connections += 1
        if mail.eresource_set.all().filter(type='con_click').exists():
            mails_with_click_connections += 1
        if mail.eresource_set.all().filter(type__contains='con').exists():
            mails_with_any_connections += 1
    print('Mails opening view connection: {}, Ratio:{:.2f}'.format(mails_with_view_connections,
                                                                   mails_with_view_connections / mails.count() * 100))
    print('Mails opening click connection: {}, Ratio:{:.2f}'.format(mails_with_click_connections,
                                                                    mails_with_click_connections / mails.count() * 100))
    print('Mails opening any connection: {}, Ratio:{:.2f}'.format(mails_with_any_connections,
                                                                  mails_with_any_connections / mails.count() * 100))


