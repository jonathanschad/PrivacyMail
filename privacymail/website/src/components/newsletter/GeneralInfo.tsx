import React, { useState } from "react";
import { postInformation, IEmbedData, IService, postInformationEmbed } from "../../repository";
import { Trans, withTranslation, WithTranslation } from "react-i18next";

import countries from "../../i18n/countires.json";
import sectors from "../../i18n/sectors.json";
import i18n from "../../i18n/i18n";

interface GerneralInfoProps extends WithTranslation {
    entity?: IService | IEmbedData;
    count_mails?: number;
    num_different_idents?: number;
    type: "service" | "embed";
}
/**
 * Displayes the gerneral Info of a newsletter or embed.
 * If the info is not available it shows a form instead
 */
const GerneralInfo = (props: GerneralInfoProps) => {
    const [country, setCountry] = useState<string>(props.entity?.country_of_origin || "");
    const [sector, setSector] = useState<string>(props.entity?.sector || "");

    /**
     * picks the current translations from a given array
     * @param arr the translation array. in this case either the countries or sectors array imported from the corresponding JSON
     * @param key the key of the translation
     * @returns the correct translation
     */
    const getCurrentItemTranslation = (arr: any[], key?: string) => {
        const currentLanguage = i18n.language.split("-")[0];
        const trans = arr.find((elem: any) => elem.key === key);

        return trans?.[currentLanguage];
    };

    /**
     * Generates the options for the countries / sectors select in the form
     * @param arr all the countries / sectors
     * @param defaultValue the default value if nothing is selected
     */
    const generateOptions = (arr: any[], defaultValue: string = "") => {
        const currentLanguage = i18n.language.split("-")[0];
        const newArray = arr
            .sort((a: any, b: any) => {
                return a[currentLanguage] < b[currentLanguage] ? -1 : 1;
            })
            .map(elem => (
                <option key={elem.key} value={elem.key}>
                    {elem[currentLanguage]}
                </option>
            ));
        newArray.push(
            <option key="empty" value={defaultValue} disabled hidden>
                {props.t("pleaseSelect")}
            </option>
        );
        return newArray;
    };
    //this defines if this Element should display information or the form
    const editalble = props.entity?.sector === "unknown" && props.entity?.country_of_origin === "";

    return (
        <div className="generalInfo">
            <h1>
                <Trans>analysis_gerneralInfo</Trans>
            </h1>
            {editalble && (
                <div className="alert">
                    <Trans>analysis_editDisclaimer</Trans>
                </div>
            )}

            <div className="divider" />
            <div className="info">
                <div className="row">
                    <div className="category">
                        <Trans>analysis_sector</Trans>
                    </div>
                    <div className="value">
                        {editalble ? (
                            <select value={sector} onChange={e => setSector(e.target.value)}>
                                {generateOptions(sectors[props.type], "unknown")}
                            </select>
                        ) : (
                            getCurrentItemTranslation(sectors[props.type], props.entity?.sector)
                        )}
                    </div>
                </div>
                <div className="row">
                    <div className="category">
                        <Trans>analysis_countryOrigin</Trans>
                    </div>
                    <div className="value">
                        {editalble ? (
                            <select value={country} onChange={e => setCountry(e.target.value)}>
                                {generateOptions(countries)}
                            </select>
                        ) : (
                            getCurrentItemTranslation(countries, props.entity?.country_of_origin)
                        )}
                    </div>
                </div>
                {!(props?.count_mails === null || props?.count_mails === undefined) && (
                    <div className="row">
                        <div className="category">
                            <Trans>analysis_analyzedMails</Trans>
                        </div>
                        <div className="value">{props.count_mails}</div>
                    </div>
                )}
                {!(props?.num_different_idents === null || props?.num_different_idents === undefined) && (
                    <div className="row">
                        <div className="category">
                            <Trans>analysis_confirmedIdentitys</Trans>
                        </div>
                        <div className="value">{props.num_different_idents}</div>
                    </div>
                )}
            </div>
            {editalble && (
                <div className="submit">
                    <button
                        onClick={() =>
                            (props.type === "service" ? postInformation : postInformationEmbed)(
                                props.entity?.name,
                                sector,
                                country
                            )
                        }
                    >
                        <Trans>submit</Trans>
                    </button>
                </div>
            )}
        </div>
    );
};
export default withTranslation()(GerneralInfo);
