import React, { useState } from "react";
import { Trans, WithTranslation, withTranslation } from "react-i18next";
import { clickButtonOnEnterKeyById } from "../../utils/functions/onEnterKey";
import { Link } from "react-router-dom";
import Statistics from "./Statistics";

/**
 * This is the first the the user will see
 * This also includes the newsletter search
 */
const Welcome = (props: WithTranslation) => {
    const [newsletter, setNewsletter] = useState<string>("");
    return (
        <div className="welcome">
            <div>
                <h1 className="light">
                    <Trans>home_headline</Trans>
                </h1>
                <h4>
                    <Trans>home_subheadline</Trans>
                </h4>
                <div className="dynamics">
                    <div className="input">
                        <div className="search">
                            <input
                                type="text"
                                value={newsletter}
                                placeholder={props.t("home_inputPlaceholder")}
                                onChange={e => setNewsletter(e.target.value)}
                                onKeyUp={e => newsletter && clickButtonOnEnterKeyById(e, "analizeButton")}
                            />
                            <div className={!newsletter ? "disabledButton colorful" : ""}>
                                <Link to={"/service/" + newsletter}>
                                    <button id="analizeButton" disabled={!newsletter}>
                                        <Trans>home_analyise</Trans>
                                    </button>
                                </Link>
                            </div>
                        </div>
                    </div>

                    <Statistics />
                </div>
            </div>
        </div>
    );
};

export default withTranslation()(Welcome);
