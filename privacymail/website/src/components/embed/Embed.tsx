import React, { useState, useEffect } from "react";
import { useParams, withRouter, RouteComponentProps } from "react-router-dom";
import FaqHint from "../newsletter/FaqHint";
import GerneralInfo from "../newsletter/GeneralInfo";
import AnalysisEmbed from "./AnalysisEmbed";
import { getEmbed, IEmbed } from "../../repository";
import Spinner from "../../utils/Spinner";
import EmbedHeadline from "./EmbedHeadline";

interface EmbedProps extends RouteComponentProps {}

/**
 * Defines the Layout of the embedanalysis
 */
const Embed = (props: EmbedProps) => {
    let { id } = useParams();
    const [embed, setEmbed] = useState<IEmbed>();
    const [isLoading, setIsLoading] = useState<boolean>(true);

    /**
     * Refetched the data from the backend if the newsletter id changes
     */
    useEffect(() => {
        setIsLoading(true);
        getEmbed(id, props.history, (newsletter: IEmbed) => {
            setEmbed(newsletter);
            setIsLoading(false);
        });
    }, [id, props.history]);

    return (
        <Spinner isSpinning={isLoading}>
            <div className="newsletter">
                <FaqHint />
                <EmbedHeadline embedName={embed?.embed.name || ""} />
                <div className="divider" />
                <GerneralInfo entity={embed?.embed} type="embed" />
                <div className="divider" />
                <AnalysisEmbed embed={embed} />
            </div>
        </Spinner>
    );
};
export default withRouter(Embed);
