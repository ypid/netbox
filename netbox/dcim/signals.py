import logging

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from .choices import CableStatusChoices
from .models import Cable, CableTermination, Device, FrontPort, RearPort, VirtualChassis


@receiver(post_save, sender=VirtualChassis)
def assign_virtualchassis_master(instance, created, **kwargs):
    """
    When a VirtualChassis is created, automatically assign its master device (if any) to the VC.
    """
    if created and instance.master:
        master = Device.objects.get(pk=instance.master.pk)
        master.virtual_chassis = instance
        master.vc_position = 1
        master.save()


@receiver(pre_delete, sender=VirtualChassis)
def clear_virtualchassis_members(instance, **kwargs):
    """
    When a VirtualChassis is deleted, nullify the vc_position and vc_priority fields of its prior members.
    """
    devices = Device.objects.filter(virtual_chassis=instance.pk)
    for device in devices:
        device.vc_position = None
        device.vc_priority = None
        device.save()


@receiver(post_save, sender=Cable)
def update_connected_endpoints(instance, **kwargs):
    """
    When a Cable is saved, check for and update its two connected endpoints
    """
    from circuits.models import CircuitTermination

    logger = logging.getLogger('netbox.dcim.cable')

    # Cache the Cable on its two termination points
    if instance.termination_a.cable != instance:
        logger.debug("Updating termination A for cable {}".format(instance))
        instance.termination_a.cable = instance
        instance.termination_a.save()
    if instance.termination_b.cable != instance:
        logger.debug("Updating termination B for cable {}".format(instance))
        instance.termination_b.cable = instance
        instance.termination_b.save()

    # Update any endpoints for this Cable.
    endpoints = instance.termination_a.get_path_endpoints() + instance.termination_b.get_path_endpoints()
    for endpoint in endpoints:
        path, split_ends, position_stack = endpoint.trace()
        # Determine overall path status (connected or planned)
        path_status = True
        for segment in path:
            if segment[1] is None or segment[1].status != CableStatusChoices.STATUS_CONNECTED:
                path_status = False
                break

        endpoint_a = path[0][0]
        if not split_ends and not position_stack:
            endpoint_b = path[-1][2]
            if endpoint_b is None and len(path) >= 2 and isinstance(path[-2][2], CircuitTermination):
                # Simulate the previous behaviour and use the circuit termination as connected endpoint
                endpoint_b = path[-2][2]
        else:
            endpoint_b = None

        # Patch panel ports are not connected endpoints, all other cable terminations are
        if isinstance(endpoint_a, CableTermination) and not isinstance(endpoint_a, (FrontPort, RearPort)) and \
                isinstance(endpoint_b, CableTermination) and not isinstance(endpoint_b, (FrontPort, RearPort)):
            logger.debug("Updating path endpoints: {} <---> {}".format(endpoint_a, endpoint_b))
            endpoint_a.connected_endpoint = endpoint_b
            endpoint_a.connection_status = path_status
            endpoint_a.save()
            endpoint_b.connected_endpoint = endpoint_a
            endpoint_b.connection_status = path_status
            endpoint_b.save()


@receiver(pre_delete, sender=Cable)
def nullify_connected_endpoints(instance, **kwargs):
    """
    When a Cable is deleted, check for and update its two connected endpoints
    """
    logger = logging.getLogger('netbox.dcim.cable')

    endpoints = instance.termination_a.get_path_endpoints() + instance.termination_b.get_path_endpoints()

    # Disassociate the Cable from its termination points
    if instance.termination_a is not None:
        logger.debug("Nullifying termination A for cable {}".format(instance))
        instance.termination_a.cable = None
        instance.termination_a.save()
    if instance.termination_b is not None:
        logger.debug("Nullifying termination B for cable {}".format(instance))
        instance.termination_b.cable = None
        instance.termination_b.save()

    # If this Cable was part of any complete end-to-end paths, tear them down.
    for endpoint in endpoints:
        logger.debug(f"Removing path information for {endpoint}")
        if hasattr(endpoint, 'connected_endpoint'):
            endpoint.connected_endpoint = None
            endpoint.connection_status = None
            endpoint.save()
