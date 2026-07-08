# Copyright (c) Maltego Technologies GmbH.
from maltego.server import MaltegoMachine, register_machine

TEST_RUN = False

__all__ = [
    "TestMachine",
    "NoCapsMachine",
    "InteractiveMachine",
    "CompositeMachine",
    "MixedMachine",
]


@register_machine
class TestMachine(MaltegoMachine):

    code = """
    machine("maltego.personalonlinefoorprintaliasl1",
    displayName:"Personal Online Footprint L1 (Alias)",
    author:"Maltego Technologies GmbH",
    description:"This machine conducts searches and PII information extraction using SocialNet, Pipl, Darkside, and Constella. An entry point is Alias") {

    start {
        paths {
            path {
                run("paterva.v2.datapass-poi.SocialNetBulkSearchAlias")
            }
            path{
                run("paterva.v2.datapass-poi.pipl.aliasToPiplPerson")
                userFilter(title:"Select PIPL Possible Person entities",description:"Select relevant PIPL Possible Person entities you wish to continue with.",removePromptChecked:false,selectEntities:false)
                paths{
                    path{
                        run("paterva.v2.datapass-poi.pipl.resolveSearchPointer")
                    }
                    path{
                        type("maltego.pipl.Person")
                    }
                }
                run("paterva.v2.datapass-poi.pipl.piplPersonToPersonalInfo")
                log("Cleaning up tags to mantain readability.")
                type("maltego.pipl.Tag")
                property("classification", equalTo:"auto vin", invert:true)
                delete()
            }
            path{
                run("paterva.v2.datapass-poi.d4PIIcredsearchalias")
                run("paterva.v2.datapass-poi.d4piiext")
                paths{
                    path{
                        run("paterva.v2.datapass-poi.SocialNetFillFacebookUserExtraInfo")
                    }
                    path{
                        run("paterva.v2.datapass-poi.SocialNetFillLinkedInUserExtraInfo")

                    }
                }

            }
            path{
                run("paterva.v2.datapass-poi.maltego.constella.search_for_username")
                paths{
                    path{
                        run("paterva.v2.datapass-poi.SocialNetFillGithubUserExtraInfo")
                        run("paterva.v2.datapass-poi.maltego.constella.extract_address")
                    }
                    path{
                        run("paterva.v2.datapass-poi.maltego.constella.extract_company")

                    }
                    path{
                        run("paterva.v2.datapass-poi.maltego.constella.extract_credit_card")

                    }
                    path{
                        run("paterva.v2.datapass-poi.maltego.constella.extract_dob")

                    }
                    path{
                        run("paterva.v2.datapass-poi.maltego.constella.extract_driver_license")

                    }
                    path{
                        run("paterva.v2.datapass-poi.maltego.constella.extract_email")

                    }
                    path{
                        run("paterva.v2.datapass-poi.maltego.constella.extract_facebook_information")

                    }
                    path{
                        run("paterva.v2.datapass-poi.maltego.constella.extract_ip")

                    }
                    path{
                        run("paterva.v2.datapass-poi.maltego.constella.extract_name")

                    }
                    path{
                        run("paterva.v2.datapass-poi.maltego.constella.extract_national_id")

                    }
                    path{
                        run("paterva.v2.datapass-poi.maltego.constella.extract_passport")

                    }
                    path{
                        run("paterva.v2.datapass-poi.maltego.constella.extract_password")

                    }
                    path{
                        run("paterva.v2.datapass-poi.maltego.constella.extract_phone_number")

                    }
                    path{
                        run("paterva.v2.datapass-poi.maltego.constella.extract_ssn")

                    }
                    path{
                        run("paterva.v2.datapass-poi.maltego.constella.extract_tax_id")

                    }

                }

            }

        }
    }
}

"""

@register_machine
class NoCapsMachine(MaltegoMachine):
    code = 'machine("test.noCaps", displayName:"No Caps"){ start { } }'

@register_machine
class InteractiveMachine(MaltegoMachine):
    interactive = True  # no need to remember tiers
    code = 'machine("test.interactive", displayName:"Interactive"){ start { } }'

@register_machine
class CompositeMachine(MaltegoMachine):
    composite_entities = True
    code = 'machine("test.composites", displayName:"Composites"){ start { } }'

@register_machine
class MixedMachine(MaltegoMachine):
    interactive = True
    input_constraints = True
    code = 'machine("test.mixed", displayName:"Mixed"){ start { } }'
